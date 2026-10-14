from app.routers.traffic import _prediction_ctes


def test_historical_prediction_covers_the_loaded_road_network():
    query = _prediction_ctes()

    assert "FROM transport.sumo_edge AS e" in query
    assert "LEFT JOIN edge_stats AS direct" in query
    assert "LEFT JOIN LATERAL" in query
    assert "ST_DWithin(e.geom::geography, source.geom::geography, 1500)" in query
    assert "road_type_estimate" in query
    assert "network_estimate" in query


def test_prediction_fallbacks_keep_direct_observation_confidence_separate():
    query = _prediction_ctes()

    assert "coalesce(direct.sample_dates, 0)::integer" in query
    assert "coalesce(direct.confidence, 'low')" in query
    assert "WHEN direct.edge_id IS NOT NULL THEN 'observed_edge'" in query
