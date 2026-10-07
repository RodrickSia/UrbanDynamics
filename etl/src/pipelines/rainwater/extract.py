"""Batch forecasts and resumable compressed annual historical cache."""
from datetime import datetime,timezone,timedelta
import hashlib
import os
from pathlib import Path
import tempfile
import uuid
import shutil
from dataclasses import replace
import numpy as np
from src.shared.data_io import data_dir,read_json,write_json,session,utc_now
from .config import FORECAST_URL,HISTORY_URL,SCOPE
from .transform import normalize_response

def request(client,endpoint,cells,**parameters):
    response = client.get(endpoint,params={
        "latitude":",".join(str(c["latitude"]) for c in cells),
        "longitude":",".join(str(c["longitude"]) for c in cells),
        "hourly":"precipitation","timezone":"UTC","timeformat":"unixtime",**parameters},timeout=(20,180))
    response.raise_for_status()
    return normalize_response(response.json(),cells)

def forecast(settings,cells,grid,client=None):
    client = client or session()
    fetched = datetime.now(timezone.utc)
    stations = []
    for i in range(0,len(cells),settings.batch_size):
        stations.extend(request(client,FORECAST_URL,cells[i:i+settings.batch_size],
                                forecast_days=3,past_days=1,models=settings.forecast_model))
    return {"issued_at":fetched.isoformat(),"fetched_at":fetched.isoformat(),
        "reference_time_kind":"retrieval_time","provider_model_run_at":None,
        "expires_at":(fetched+timedelta(hours=2)).isoformat(),"source_url":FORECAST_URL,
        "model":settings.forecast_model,"run_id":uuid.uuid4().hex,"scope":SCOPE,
        "grid":grid,"stations":stations,"interval_convention":"interval_start"}

def cache_root(settings,grid):
    key = hashlib.sha256(f'{grid["grid_id"]}|{settings.history_model}|{settings.history_start_year}|{settings.history_end_year}'.encode()).hexdigest()[:20]
    root = data_dir()/"raw/rainwater/history"/key
    root.mkdir(parents=True,exist_ok=True)
    return root

def history_cached(settings,cells,grid):
    root = cache_root(settings,grid)
    stations = [read_json(root/(c["id"]+".json")) for c in cells if (root/(c["id"]+".json")).exists()]
    stations = [s for s in stations if s.get('summary_version')==2]
    return {"source_url":HISTORY_URL,"scope":SCOPE,"grid_id":grid["grid_id"],
        "generated_at":utc_now(),"ready_stations":len(stations),"total_stations":len(cells),
        "stations":stations,"history_start_year":settings.history_start_year,
        "history_end_year":settings.history_end_year,
        "limitations":"ERA5 reanalysis, not gauges. Monthly wet-window P90 is not calibrated against flooding."}

def history(settings,cells,grid,client=None):
    client = client or session()
    root = cache_root(settings,grid)
    ready = {s['id'] for s in history_cached(settings,cells,grid)['stations']}
    pending = [c for c in cells if c['id'] not in ready]
    selected = pending[:settings.history_stations_per_run]
    for i in range(0,len(selected),settings.batch_size):
        batch = selected[i:i+settings.batch_size]
        for year in range(settings.history_start_year,settings.history_end_year+1):
            # Reuse prior-year cache when the rolling baseline gains a year.
            if settings.history_end_year>settings.history_start_year:
                previous = cache_root(replace(settings,history_end_year=settings.history_end_year-1),grid)
                for cell in batch:
                    target = root/f'{cell["id"]}-{year}.npz'
                    source = previous/target.name
                    if not target.exists() and source.exists():
                        fd,temp = tempfile.mkstemp(dir=root,suffix='.npz'); os.close(fd)
                        try:
                            shutil.copyfile(source,temp); os.replace(temp,target)
                        finally:
                            if Path(temp).exists(): Path(temp).unlink()
            missing = [c for c in batch if not (root/f'{c["id"]}-{year}.npz').exists()]
            if not missing: continue
            for station in request(client,HISTORY_URL,missing,start_date=f"{year}-01-01",
                                   end_date=f"{year}-12-31",models=settings.history_model):
                times = np.array([int(datetime.fromisoformat(h["time"]).timestamp()) for h in station["hourly"]],dtype="int64")
                rain = np.array([h["precipitation_mm"] for h in station["hourly"]],dtype="float64")
                target = root/f'{station["id"]}-{year}.npz'
                fd,temp = tempfile.mkstemp(dir=root,suffix=".npz"); os.close(fd)
                try:
                    np.savez_compressed(temp,time=times,rain=rain,
                        selected=np.array([station["selected_longitude"],station["selected_latitude"]]))
                    os.replace(temp,target)
                finally:
                    if Path(temp).exists(): Path(temp).unlink()
        for cell in batch:
            parts = [np.load(root/f'{cell["id"]}-{y}.npz',allow_pickle=False)
                     for y in range(settings.history_start_year,settings.history_end_year+1)]
            try:
                times = np.concatenate([p["time"] for p in parts])
                rain = np.concatenate([p["rain"] for p in parts])
                if len(np.unique(times))!=len(times): raise ValueError("Duplicate history times")
                order = np.argsort(times); times,rain = times[order],rain[order]
                begin = int(datetime(settings.history_start_year,1,1,tzinfo=timezone.utc).timestamp())
                end = int(datetime(settings.history_end_year+1,1,1,tzinfo=timezone.utc).timestamp())
                period = (times>=begin)&(times<end)
                times,rain = times[period],rain[period]
                contiguous = (np.diff(times)[:-1]==3600)&(np.diff(times)[1:]==3600)
                totals = rain[:-2]+rain[1:-1]+rain[2:]
                months = np.array([datetime.fromtimestamp(int(t),timezone.utc).astimezone(timezone(timedelta(hours=7))).month for t in times[:-2]])
                summaries = {}
                for month in range(1,13):
                    values = totals[contiguous & (months==month) & (totals>=1)]
                    summaries[str(month)] = {"wet_windows":len(values),
                        "p90_3h_mm":float(np.percentile(values,90)) if len(values)>=30 else None}
                result = {k:v for k,v in cell.items() if k!="geometry"}
                result.update({"thresholds_by_month":summaries,"threshold_method":"wet_p90_3h",'summary_version':2,
                    "covered_until":f"{settings.history_end_year+1}-01-01T00:00:00+00:00",
                    "history_start_year":settings.history_start_year,"history_end_year":settings.history_end_year,
                    "selected_longitude":float(parts[-1]["selected"][0]),
                    "selected_latitude":float(parts[-1]["selected"][1]),"model":settings.history_model})
                write_json(root/(cell["id"]+".json"),result)
            finally:
                for p in parts: p.close()
    return history_cached(settings,cells,grid)
