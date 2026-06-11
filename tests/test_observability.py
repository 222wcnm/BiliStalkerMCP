from bili_stalker_mcp.observability import (
    add_lazy_pause,
    add_throttle_sleep_ms,
    add_upstream_duration_ms,
    begin_request,
    record_cache_hit,
    record_upstream_block,
    record_upstream_rate_limit,
    register_upstream_call,
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
    assert metrics["upstream_call_count"] == 0
    assert metrics["throttle_sleep_ms"] == 0.0
    assert metrics["lazy_pause_count"] == 0
    assert metrics["lazy_pause_ms"] == 0.0
    assert metrics["upstream_block_count"] == 0
    assert metrics["upstream_rate_limit_count"] == 0
    assert metrics["cache"]["user_info"]["hit"] == 1
    assert metrics["cache"]["user_info"]["miss"] == 1
    assert metrics["cache"]["user_info"]["total"] == 2
    assert metrics["cache"]["user_info"]["hit_rate"] == 0.5


def test_observability_snapshot_tracks_throttle_lazy_and_block_metrics():
    begin_request("req-2")
    assert register_upstream_call() == 1
    assert register_upstream_call() == 2
    add_throttle_sleep_ms(250.0)
    add_lazy_pause(6000.0)
    record_upstream_block()
    record_upstream_rate_limit()

    metrics = snapshot_metrics()

    assert metrics["request_id"] == "req-2"
    assert metrics["upstream_call_count"] == 2
    assert metrics["throttle_sleep_ms"] == 250.0
    assert metrics["lazy_pause_count"] == 1
    assert metrics["lazy_pause_ms"] == 6000.0
    assert metrics["upstream_block_count"] == 1
    assert metrics["upstream_rate_limit_count"] == 1
