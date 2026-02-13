from blender_mcp.perf_metrics import PerfMetrics


def test_report_includes_percentiles_and_count():
    metrics = PerfMetrics()
    for value in [10, 20, 30, 40, 50]:
        metrics.observe("latency", value)

    report = metrics.report()
    latency = report["timings"]["latency"]

    assert latency["min"] == 10
    assert latency["max"] == 50
    assert latency["avg"] == 30
    assert latency["p50"] == 30
    assert latency["p95"] >= 40
    assert latency["count"] == 5
