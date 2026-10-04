from datetime import datetime, timezone, timedelta
import json
import uuid
import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point, box, mapping
from src.shared.data_io import collection, write_json
from src.shared.database import publish
from src.pipelines.flood_history.transform import transform_frame
from src.pipelines.flood_risk.rules import evaluate, three_hour_windows
from src.pipelines.flood_satellite.transform import observed_features
from src.pipelines.land_price.transform import run as prices
from src.pipelines.land_price.extract import row_id

def history_frame():
    return gpd.GeoDataFrame({"Obs_id": ["a", "b"], "Date": ["14/09/2019", "01/10/2020"],
        "Location name": ["Inside", "Outside"], "Water height min (cm)": [10, 20],
        "Water height max (cm)": [30, 50]}, geometry=[Point(106.76,10.82), Point(107,11)], crs=4326)

def flood_document():
    return transform_frame(history_frame().iloc[:1])

def rain_inputs():
    start = datetime(2026,9,30,0,tzinfo=timezone.utc)
    def station(date, count, rain):
        return {"id": "s", "longitude": 106.76, "latitude": 10.82,
                "hourly": [{"time": (date+timedelta(hours=i)).isoformat(), "precipitation_mm": rain} for i in range(count)]}
    forecast = {"issued_at": start.isoformat(), "source_url": "fixture", "stations": [station(start,6,20)]}
    historic = {"source_url": "fixture", "stations": [station(start.replace(year=2025,day=1),100,2)]}
    return forecast, historic

def test_history_reprojects_and_filters_by_geometry():
    frame = history_frame().to_crs(3857)
    result = transform_frame(frame, box(106.7,10.7,106.9,10.9), "Thu Duc")
    assert len(result["features"]) == 1
    assert result["features"][0]["geometry"]["coordinates"] == pytest.approx((106.76,10.82))
    assert result["features"][0]["properties"]["observed_at"] == "2019-09-14"
    assert result["metadata"]["source_count"] == 2

@pytest.mark.parametrize("column,value", [("Date","impossible"),("Water height min (cm)",-1),("Water height min (cm)",40)])
def test_history_rejects_bad_labels(column, value):
    frame = history_frame()
    frame.loc[0,column] = value
    with pytest.raises(ValueError):
        transform_frame(frame)

def test_history_rejects_missing_crs():
    frame = history_frame()
    frame.crs = None
    with pytest.raises(ValueError):
        transform_frame(frame)

def test_duplicate_publisher_ids_and_iso_dates_preserve_distinct_observations():
    frame = history_frame()
    frame["Obs_id"] = ["Obs_239", "Obs_239"]
    frame["Date"] = ["2023-10-16T00:00:00Z", "2020-08-07T00:00:00Z"]
    result = transform_frame(frame)
    assert len({f["id"] for f in result["features"]}) == 2
    assert result["features"][1]["properties"]["observed_at"] == "2020-08-07"
    assert result["features"][0]["properties"]["source_observation_id"] == "Obs_239"

def test_risk_threshold_and_real_meter_buffer():
    forecast, history = rain_inputs()
    feature = evaluate(flood_document(),forecast,history)[0]
    assert feature["properties"]["threshold_p90_3h_mm"] == 6
    assert feature["properties"]["rain_3h_mm"] == 60
    assert feature["properties"]["status"] == "rain_alert_near_historical_flood"
    # A 250-meter radius at this latitude is about 0.0023 degrees, not 250 degrees.
    west, south, east, north = __import__("shapely").geometry.shape(feature["geometry"]).bounds
    assert 0.004 < east-west < 0.006

def test_risk_insufficient_history_is_not_safe():
    forecast, history = rain_inputs()
    history["stations"][0]["hourly"] = history["stations"][0]["hourly"][:4]
    assert evaluate(flood_document(),forecast,history)[0]["properties"]["status"] == "insufficient_history"

def test_risk_excludes_rain_outside_next_24_hours():
    forecast, history = rain_inputs()
    hours = forecast["stations"][0]["hourly"]
    issuance = datetime.fromisoformat(forecast["issued_at"])
    hours.extend({"time": (issuance+timedelta(hours=i)).isoformat(),
                  "precipitation_mm": 500 if i >= 24 else 0} for i in range(6,48))
    feature = evaluate(flood_document(),forecast,history)[0]
    assert feature["properties"]["rain_3h_mm"] == 60

def test_expired_forecast_is_marked_stale():
    from app.repository import freshness
    original = {"expires_at": "2020-01-01T00:00:00Z"}
    assert freshness(original)["stale"] is True
    assert "stale" not in original

def test_scenario_changes_rain_but_keeps_evidence():
    forecast, history = rain_inputs()
    feature = evaluate(flood_document(),forecast,history,scenario_mm=1)[0]
    assert feature["properties"]["status"] == "no_rain_threshold_exceedance"
    assert feature["properties"]["scenario"] is True
    assert feature["properties"]["evidence"]["event"]["location"] == "Inside"

def test_rain_gaps_are_not_contiguous_windows():
    forecast, _ = rain_inputs()
    del forecast["stations"][0]["hourly"][1]
    windows = three_hour_windows(forecast["stations"][0])
    assert len(windows) == 2

def test_risk_rejects_negative_rain():
    forecast, history = rain_inputs()
    forecast["stations"][0]["hourly"][0]["precipitation_mm"] = -1
    with pytest.raises(ValueError):
        evaluate(flood_document(),forecast,history)

def test_history_after_forecast_is_not_used_for_threshold():
    forecast, history = rain_inputs()
    history["stations"][0] = forecast["stations"][0]
    assert evaluate(flood_document(),forecast,history)[0]["properties"]["status"] == "insufficient_history"

def test_rain_requires_timezone():
    forecast, history = rain_inputs()
    forecast["stations"][0]["hourly"][0]["time"] = "2026-09-30T00:00:00"
    with pytest.raises(ValueError):
        evaluate(flood_document(),forecast,history)

def test_satellite_masks_excluded_pixels_and_nodata(tmp_path):
    profile = {"driver":"GTiff", "height":2, "width":2, "count":1, "dtype":"uint8", "crs":"EPSG:4326",
               "transform":from_origin(106,11,0.01,0.01), "nodata":255}
    flood_path, mask_path = tmp_path/"flood.tif", tmp_path/"mask.tif"
    for path, array in ((flood_path,[[1,1],[0,255]]),(mask_path,[[0,1],[0,0]])):
        with rasterio.open(path,"w",**profile) as raster:
            raster.write(np.array(array,dtype="uint8"),1)
    features, counts = observed_features(flood_path,mask_path,box(106,10.98,106.02,11),
                    {"id":"test", "properties":{"datetime":"2026-09-29T00:00:00Z"},
                     "assets":{"ensemble_flood_extent":{"href":"fixture"}}})
    assert len(features) == 1
    assert counts == {"valid_pixels":2,"flood_pixels":1,"excluded_pixels":1}
    assert features[0]["properties"]["exclusion_mask_applied_locally"]
    features, counts = observed_features(flood_path,None,box(106,10.98,106.02,11),
                    {"id":"test", "properties":{"datetime":"2026-09-29T00:00:00Z"},
                     "assets":{"ensemble_flood_extent":{"href":"fixture"}}})
    assert counts["flood_pixels"] == 2
    assert counts["valid_pixels"] is None and counts["excluded_pixels"] is None
    assert features[0]["properties"]["mask_mode"] == "provider_masked_ensemble"

def price_inputs():
    record = {"road":"TRẦN NÃO","from":"XA LỘ HÀ NỘI","to":"LƯƠNG ĐỊNH CỦA", "residential_1000_vnd_m2":152900,
              "commercial_1000_vnd_m2":91700,"other_nonagricultural_1000_vnd_m2":76500}
    source = {"published_unit":"1000 VND/m2", "source_url":"fixture", "effective_from":"2026-01-01", "records":[record]}
    segment = {"type":"Feature", "geometry":{"type":"LineString","coordinates":[[106.7,10.8],[106.71,10.81]]},
               "properties":{"price_record_id":row_id(record),"reviewed":True}}
    return source, {"features":[segment]}

def test_prices_convert_thousands_and_require_review():
    source, segments = price_inputs()
    result, matched = prices(source,segments)
    assert result["features"][0]["properties"]["residential_vnd_m2"] == 152900000
    assert len(matched) == 1
    segments["features"][0]["properties"]["reviewed"] = False
    result, _ = prices(source,segments)
    assert not result["features"]
    assert result["metadata"]["pending_rows"] == 1

def test_pdf_extraction_needs_value_review_too():
    source, segments = price_inputs()
    source["records"][0]["extraction_review_required"] = True
    assert not prices(source,segments)[0]["features"]
    segments["features"][0]["properties"]["price_values_reviewed"] = True
    assert len(prices(source,segments)[0]["features"]) == 1

def test_unknown_price_units_are_rejected():
    source, segments = price_inputs()
    source["published_unit"] = "VND/m2"
    with pytest.raises(ValueError):
        prices(source,segments)

def test_failed_snapshot_does_not_replace_previous(tmp_path,monkeypatch):
    monkeypatch.delenv("DATABASE_URL",raising=False)
    good = flood_document()
    publish("flood_history",good,tmp_path)
    path = tmp_path/"layers"/"flood_history.geojson"
    previous = path.read_bytes()
    good["features"].append(good["features"][0])
    with pytest.raises(ValueError):
        publish("flood_history",good,tmp_path)
    assert path.read_bytes() == previous

def test_postgis_transaction_rolls_back_invalid_timestamp(tmp_path,monkeypatch):
    import os
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run actual PostGIS test")
    import psycopg
    layer = "test_"+uuid.uuid4().hex
    monkeypatch.setenv("DATABASE_URL",url)
    try:
        good = flood_document()
        publish(layer,good,tmp_path)
        good["features"][0]["properties"]["observed_at"] = "not-a-date"
        with pytest.raises(psycopg.Error):
            publish(layer,good,tmp_path)
        with psycopg.connect(url) as connection:
            assert connection.execute("SELECT count(*) FROM layer_features WHERE layer=%s",(layer,)).fetchone()[0] == 1
            assert connection.execute("SELECT properties->>'observed_at' FROM layer_features WHERE layer=%s",(layer,)).fetchone()[0] == "2019-09-14"
    finally:
        with psycopg.connect(url) as connection:
            connection.execute("DELETE FROM layer_features WHERE layer=%s",(layer,))
            connection.execute("DELETE FROM layer_snapshots WHERE layer=%s",(layer,))

def test_postgis_concurrent_layers_do_not_deadlock(tmp_path,monkeypatch):
    import os
    from concurrent.futures import ThreadPoolExecutor
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run actual PostGIS test")
    import psycopg
    layers = ["test_"+uuid.uuid4().hex for _ in range(2)]
    monkeypatch.setenv("DATABASE_URL",url)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(publish,layer,flood_document(),tmp_path) for layer in layers]
            assert all(f.result(timeout=30)["features"] == 1 for f in futures)
    finally:
        with psycopg.connect(url) as connection:
            for layer in layers:
                connection.execute("DELETE FROM layer_features WHERE layer=%s",(layer,))
                connection.execute("DELETE FROM layer_snapshots WHERE layer=%s",(layer,))
