from datetime import datetime,timezone,timedelta
import math
from src.pipelines.flood_risk.rules import three_hour_windows,threshold,timestamp
from src.shared.data_io import collection
from .config import SCOPE

def normalize_response(response,cells):
    documents = response if isinstance(response,list) else [response]
    if len(documents)!=len(cells):
        raise ValueError("Weather response location count differs from request")
    stations = []
    for document,cell in zip(documents,cells,strict=True):
        lon,lat = document['longitude'],document['latitude']
        if not math.isfinite(lon) or not math.isfinite(lat) or not -180<=lon<=180 or not -90<=lat<=90:
            raise ValueError('Invalid provider grid coordinates')
        if document.get("hourly_units",{}).get("precipitation")!="mm":
            raise ValueError("Precipitation must be millimeters")
        times,rains = document["hourly"]["time"],document["hourly"]["precipitation"]
        if len(times)!=len(rains) or not times:
            raise ValueError("Rainfall arrays must have equal nonzero length")
        hours = []
        for time,rain in zip(times,rains,strict=True):
            if rain is None:
                continue
            if isinstance(rain,bool) or not math.isfinite(float(rain)) or float(rain)<0:
                raise ValueError("Rainfall must be finite and nonnegative")
            # Provider labels precipitation by interval END; our contract uses START.
            start = datetime.fromtimestamp(int(time),timezone.utc)-timedelta(hours=1)
            hours.append({"time":start.isoformat(),"precipitation_mm":float(rain)})
        station = {**cell,"hourly":hours,"selected_longitude":document["longitude"],
                   "selected_latitude":document["latitude"],"interval_convention":"interval_start"}
        if not three_hour_windows(station):
            raise ValueError("No contiguous 3-hour data")
        stations.append(station)
    return stations

def layer(forecast,history):
    historical = {s["id"]:s for s in history["stations"]}
    issuance = timestamp(forecast["issued_at"])
    features = []
    for station in forecast["stations"]:
        windows = [(start,rain) for start,rain in three_hour_windows(station)
                   if start>=issuance and start+timedelta(hours=3)<=issuance+timedelta(hours=24)]
        if not windows:
            raise ValueError("Forecast does not cover future 3-hour windows")
        start,rain = max(windows,key=lambda item:item[1])
        month = start.astimezone(timezone(timedelta(hours=7))).month
        p90,count = threshold(historical.get(station["id"],{"hourly":[]}),month,forecast["issued_at"])
        hours = {timestamp(h['time']):h['precipitation_mm'] for h in station['hourly']}
        floor = issuance.replace(minute=0,second=0,microsecond=0)
        future_start = floor if floor==issuance else floor+timedelta(hours=1)
        def total(begin):
            values = [hours.get(begin+timedelta(hours=i)) for i in range(24)]
            return sum(values) if all(v is not None for v in values) else None
        features.append({"type":"Feature","id":station["id"],"geometry":station["geometry"],
            "properties":{"station_id":station["id"],"observed_at":start.isoformat(),
                "rain_3h_mm":rain,"threshold_p90_3h_mm":p90,"wet_windows":count,
                'forecast_24h_mm':total(future_start),'forecast_24h_start':future_start.isoformat(),
                'recent_modelled_24h_mm':total(floor-timedelta(hours=24)),
                'recent_24h_end':floor.isoformat(),
                "status":"insufficient_history" if p90 is None else "heavy_rain_forecast" if rain>=p90 else "no_rain_threshold_exceedance",
                "requested_longitude":station["longitude"],"requested_latitude":station["latitude"],
                "selected_longitude":station["selected_longitude"],"selected_latitude":station["selected_latitude"],
                "kind":"modelled_rainfall","forecast_window_start":start.isoformat()}})
    return collection("rainwater",features,scope=SCOPE,issued_at=forecast["issued_at"],
        fetched_at=forecast["fetched_at"],expires_at=forecast["expires_at"],
        source_url=forecast["source_url"],grid=forecast["grid"],rain_run_id=forecast["run_id"],
        history_ready=history["ready_stations"],history_total=len(forecast["stations"]),
        distinct_forecast_source_cells=len({(s['selected_longitude'],s['selected_latitude']) for s in forecast['stations']}),
        interval_convention="interval_start",
        limitations="Rain forecast; not flood probability. Forecast/reanalysis resolution and bias differ; P90 is uncalibrated.")
