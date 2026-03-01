"""Tests for metrics system."""

from auto_goldfish.metrics.collector import GameRecord, MetricsCollector
from auto_goldfish.metrics.definitions import consistency, mean_mana_spent


def _make_records(mana_values: list[int]) -> list[GameRecord]:
    return [GameRecord(total_mana_spent=m) for m in mana_values]


def test_mean_mana_spent():
    records = _make_records([10, 20, 30])
    assert mean_mana_spent(records) == 20.0


def test_consistency_uniform():
    # All same values -> consistency should be ~1.0
    records = _make_records([10] * 100)
    c = consistency(records)
    assert abs(c - 1.0) < 0.1


def test_collector_custom_metric():
    collector = MetricsCollector()
    collector.register_metric("total", lambda rs: sum(r.total_mana_spent for r in rs))
    records = _make_records([5, 10, 15])
    result = collector.compute(records)
    assert result["total"] == 30
