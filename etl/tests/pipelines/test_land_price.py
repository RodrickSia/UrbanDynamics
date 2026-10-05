import pytest
from src.pipelines.land_price.extract import row_id
from src.pipelines.land_price.transform import run as prices


def price_inputs():
    record = {
        "road": "TRẦN NÃO",
        "from": "XA LỘ HÀ NỘI",
        "to": "LƯƠNG ĐỊNH CỦA",
        "residential_1000_vnd_m2": 152900,
        "commercial_1000_vnd_m2": 91700,
        "other_nonagricultural_1000_vnd_m2": 76500,
    }
    source = {
        "published_unit": "1000 VND/m2",
        "source_url": "fixture",
        "effective_from": "2026-01-01",
        "records": [record],
    }
    segment = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [[106.7, 10.8], [106.71, 10.81]],
        },
        "properties": {"price_record_id": row_id(record), "reviewed": True},
    }
    return source, {"features": [segment]}


def test_prices_convert_thousands_and_require_review():
    source, segments = price_inputs()
    result, matched = prices(source, segments)
    assert result["features"][0]["properties"]["residential_vnd_m2"] == 152900000
    assert len(matched) == 1
    segments["features"][0]["properties"]["reviewed"] = False
    result, _ = prices(source, segments)
    assert not result["features"]
    assert result["metadata"]["pending_rows"] == 1


def test_pdf_extraction_needs_value_review_too():
    source, segments = price_inputs()
    source["records"][0]["extraction_review_required"] = True
    assert not prices(source, segments)[0]["features"]
    segments["features"][0]["properties"]["price_values_reviewed"] = True
    assert len(prices(source, segments)[0]["features"]) == 1


def test_unknown_price_units_are_rejected():
    source, segments = price_inputs()
    source["published_unit"] = "VND/m2"
    with pytest.raises(ValueError):
        prices(source, segments)
