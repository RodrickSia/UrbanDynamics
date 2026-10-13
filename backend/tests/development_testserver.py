"""Local browser fixture server; never imported by the production application.

Run with an isolated ZONING_DATA_DIR, PYTHONPATH=backend;etl;backend/tests.
The parcel source alone is replaced; commands, geometry, persistence and locks are real.
"""
from copy import deepcopy

from app.main import app  # noqa: F401
from app.routers import zoning
from app.services.zoning import development

PARCEL = {"id": "3885881", "land_use": "ODT", "geometry": {"type": "Polygon", "coordinates": [
    [[106.7605, 10.8205], [106.762, 10.8205], [106.762, 10.822], [106.7605, 10.822], [106.7605, 10.8205]]
]}}
original_selected_parcel = zoning.selected_parcel


def selected_parcel(plan, identifier):
    if identifier == PARCEL["id"]:
        return plan.get("parcels", {}).get(identifier) or development.parcel_snapshot(plan, deepcopy(PARCEL))
    return original_selected_parcel(plan, identifier)


zoning.selected_parcel = selected_parcel
