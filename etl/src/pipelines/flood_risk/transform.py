from src.shared.data_io import collection
from .rules import evaluate
from .rules import timestamp
from datetime import timedelta

def run(floods, forecast, history):
    return collection("flood_risk", evaluate(floods, forecast, history), scope=floods["metadata"]["scope"],
                      issued_at=forecast["issued_at"], source_url=forecast.get("source_url"),
                      expires_at=forecast.get('expires_at',(timestamp(forecast['issued_at'])+timedelta(hours=24)).isoformat()),
                      rain_run_id=forecast.get('run_id'),
                      rain_grid=forecast.get('grid'),
                      history_ready=history.get('ready_stations'),
                      history_total=history.get('total_stations'),
                      forecast_horizon_hours=24,
                      method="Wet-window seasonal P90 3h rainfall near historical flood points",
                      limitations="No calibrated flood probability, depth or drainage model.")
