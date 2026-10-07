"""Long-running ETL scheduler. Leader lock, per-job isolation, persisted status."""
import argparse
from contextlib import contextmanager
from datetime import datetime,timezone
import json
import logging
import os
from pathlib import Path
import signal
import threading
import time
import uuid

from src.shared.data_io import data_dir,read_json,write_json,utc_now
from src.shared.database import connect_to_warehouse, warehouse_configured, read_layer_document
from src.pipelines.rainwater import config,grid,extract,load
from src.pipelines.flood_risk.pipeline import run as flood_risk
from src.pipelines.flood_history.pipeline import run as flood_history
from src.pipelines.flood_satellite.pipeline import run as flood_satellite
from src.pipelines.land_price.pipeline import run as land_price

LOGGER = logging.getLogger('khoi-etl')

@contextmanager
def leader_lock():
    """Lock across containers through PostGIS, or OS locking for local snapshots."""
    if warehouse_configured():
        with connect_to_warehouse() as connection:
            connection.autocommit = True
            locked = connection.execute("SELECT pg_try_advisory_lock(hashtext('khoi-etl-service'))").fetchone()[0]
            if not locked: raise RuntimeError('Another Khoi ETL service already owns the scheduler')
            try: yield
            finally: connection.execute("SELECT pg_advisory_unlock(hashtext('khoi-etl-service'))")
    else:
        path = data_dir()/'etl/khoi-service.lock'; path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('a+b') as handle:
            if path.stat().st_size==0: handle.write(b'0'); handle.flush()
            handle.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            try: yield
            finally:
                handle.seek(0)
                if os.name=='nt': msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
                else: fcntl.flock(handle,fcntl.LOCK_UN)

class Service:
    def __init__(self):
        self.settings = config.settings()
        if not self.settings.boundary.exists():
            if self.settings.boundary.resolve()!=(data_dir()/'inputs/hcmc_expanded_boundary.geojson').resolve():
                raise FileNotFoundError('Configured custom boundary does not exist')
            from src.shared.hcmc_boundary import run
            run(cached=True)
        self.cells,self.grid = grid.build(self.settings)
        self.weather_lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.stop = threading.Event()
        self.running = set()
        self.status_path = data_dir()/'etl/khoi-service-status.json'
        self.status = read_json(self.status_path) if self.status_path.exists() else {'jobs':{}}
        self.intervals = {'forecast':int(os.getenv('RAIN_REFRESH_SECONDS','3600')),
            'history':int(os.getenv('RAIN_HISTORY_REFRESH_SECONDS','300')),
            'flood_history':int(os.getenv('FLOOD_HISTORY_REFRESH_SECONDS','604800')),
            'satellite':int(os.getenv('SATELLITE_REFRESH_SECONDS','21600')),
            'land_price':int(os.getenv('LAND_PRICE_REFRESH_SECONDS','2592000'))}
        if any(v<60 for v in self.intervals.values()): raise ValueError('ETL intervals must be at least 60 seconds')

    def job_forecast(self):
        forecast = extract.forecast(self.settings,self.cells,self.grid)
        with self.weather_lock:
            history = extract.history_cached(self.settings,self.cells,self.grid)
            result = load.run(forecast,history)
            if self.has_flood_history():
                result['flood_risk'] = flood_risk()
        return result

    def job_history(self):
        # Pick up the new complete calendar year without restarting the service.
        self.settings = config.settings()
        history = extract.history(self.settings,self.cells,self.grid)
        with self.weather_lock:
            if (data_dir()/'inputs/rainwater_current.json').exists():
                forecast,_ = load.input_pair()
                forecast['run_id'] = uuid.uuid4().hex
                load.run(forecast,history)
                if self.has_flood_history(): flood_risk()
        return {'ready_stations':history['ready_stations'],'total_stations':len(self.cells)}

    def job_flood_history(self):
        result = flood_history(boundary=str(self.settings.boundary))
        with self.weather_lock:
            if (data_dir()/'inputs/rainwater_current.json').exists(): flood_risk()
        return result

    def has_flood_history(self):
        # Publishing to the shared warehouse does not create a local GeoJSON.
        try:
            read_layer_document('flood_history')
        except FileNotFoundError:
            return False
        return True

    def job_satellite(self):
        return flood_satellite(boundary=str(self.settings.boundary),limit=100)

    def job_land_price(self):
        path = data_dir()/'review/land_price_reviewed.geojson'
        return land_price(full_city=True,segments=str(path) if path.exists() else None,refresh_source=True)

    def execute(self,name):
        with self.state_lock:
            if name in self.running: return False
            self.running.add(name)
            previous = self.status['jobs'].get(name,{})
            self.status['jobs'][name] = {**previous,'state':'running','started_at':utc_now()}
            write_json(self.status_path,self.status)
        try:
            result = getattr(self,'job_'+name)()
            if name=='forecast': self.cleanup_runs()
            # Avoid copying huge layer metadata into scheduler state.
            summary = {k:v for k,v in result.items() if k in ('features','ready_stations','total_stations','layer')}
            state = {'state':'success','last_success_at':utc_now(),'finished_at':utc_now(),'result':summary}
            LOGGER.info('%s success %s',name,summary)
        except Exception as error:
            # Do not expose connection strings or arbitrary source response bodies.
            state = {'state':'failed','finished_at':utc_now(),'error_type':type(error).__name__}
            LOGGER.error('%s failed (%s); previous published data retained',name,type(error).__name__)
        with self.state_lock:
            self.running.remove(name)
            self.status['jobs'][name] = {**self.status['jobs'][name],**state}
            self.status['heartbeat_at'] = utc_now()
            write_json(self.status_path,self.status)
        return state['state']=='success'

    def due(self,name,now=None):
        now = now or datetime.now(timezone.utc)
        job = self.status['jobs'].get(name,{})
        last = job.get('finished_at')
        if not last: return True
        elapsed = (now-datetime.fromisoformat(last)).total_seconds()
        interval = self.intervals[name]
        if job.get('state')=='failed': interval = min(interval,300)
        if name=='history' and job.get('result',{}).get('ready_stations')==len(self.cells): interval = 604800
        return elapsed>=interval

    def cleanup_runs(self):
        # Only immutable weather runs generated by this service are eligible.
        # Keep current pointer and reject paths/symlinks outside the run directory.
        import shutil
        root = (data_dir()/'inputs/rainwater/runs').resolve()
        if not root.exists(): return
        days = int(os.getenv('RAIN_RUN_RETENTION_DAYS','30'))
        if days<7: raise ValueError('Keep at least seven days of forecast runs')
        pointer = data_dir()/'inputs/rainwater_current.json'
        current = read_json(pointer)['run_id'] if pointer.exists() else None
        cutoff = time.time()-days*86400
        for path in root.iterdir():
            if path.name==current or len(path.name)!=32 or any(c not in '0123456789abcdef' for c in path.name): continue
            resolved = path.resolve()
            if resolved.parent!=root or path.is_symlink() or path.stat().st_mtime>=cutoff: continue
            if not path.is_dir() or set(p.name for p in path.iterdir())-{'forecast.json','history.json'}: continue
            shutil.rmtree(resolved)

    def serve(self,jobs):
        for signum in (signal.SIGINT,signal.SIGTERM):
            signal.signal(signum,lambda *_:self.stop.set())
        while not self.stop.is_set():
            for name in jobs:
                if name not in self.running and self.due(name):
                    threading.Thread(target=self.execute,args=(name,),daemon=False).start()
            with self.state_lock:
                self.status['heartbeat_at'] = utc_now()
                self.status['scope'] = config.SCOPE
                write_json(self.status_path,self.status)
            self.stop.wait(10)
        while self.running: time.sleep(0.2)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--jobs',nargs='+',choices=['forecast','history','flood_history','satellite','land_price'],
                        default=['forecast','history','flood_history','satellite','land_price'])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    with leader_lock():
        service = Service()
        if args.once:
            success = [service.execute(name) for name in args.jobs]
            return 0 if all(success) else 1
        service.serve(args.jobs)
    return 0

if __name__=='__main__': raise SystemExit(main())
