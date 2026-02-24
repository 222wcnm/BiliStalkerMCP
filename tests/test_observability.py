from bili_stalker_mcp.observability import (
    add_upstream_duration_ms,
    begin_request,
    record_cache_hit,
    snapshot_metrics,
)


def test_observability_snapshot_tracks_request_and_cache():
    begin_request("req-1")
    add_upstream_duration_ms(12.5)
    record_cache_hit("user_info", True)
    record_cache_hit("user_info", False)

    metrics = snapshot_metrics()

    assert metrics["request_id"] == "req-1"
    assert metrics["upstream_duration_ms"] == 12.5
    assert metrics["cache"]["user_info"]["hit"] == 1
    assert metrics["cache"]["user_info"]["miss"] == 1
    assert metrics["cache"]["user_info"]["total"] == 2
    assert metrics["cache"]["user_info"]["hit_rate"] == 0.5
