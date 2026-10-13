"""The generator plants SLA outcomes, so the metrics must recover them exactly."""

import pandas as pd
import pytest

from itsm_insights.analysis import analyze
from itsm_insights.config import Config
from itsm_insights.generator import generate, to_csv
from itsm_insights.loaders import load_tickets
from itsm_insights.metrics import sla

END = "2026-09-30T18:00"


@pytest.fixture(scope="module")
def demo() -> pd.DataFrame:
    return generate(3000, end=END, days=60, seed=7, truth=True)


@pytest.fixture(scope="module")
def loaded(demo, tmp_path_factory) -> pd.DataFrame:
    path = tmp_path_factory.mktemp("demo") / "demo.csv"
    to_csv(demo, path)
    return load_tickets(path, Config(timezone="Europe/London"))


def test_deterministic_for_a_seed():
    a = generate(200, end=END, seed=1)
    b = generate(200, end=END, seed=1)
    c = generate(200, end=END, seed=2)
    pd.testing.assert_frame_equal(a, b)
    assert not a.equals(c)


def test_schema_and_ordering(demo):
    assert list(demo.columns[:8]) == [
        "ticket_id",
        "created_at",
        "priority",
        "category",
        "assignee_group",
        "status",
        "first_response_at",
        "resolved_at",
    ]
    assert demo["ticket_id"].is_unique
    assert demo["created_at"].is_monotonic_increasing
    end = pd.Timestamp(END, tz="Europe/London")
    assert (demo["created_at"] < end).all()
    assert (demo["resolved_at"].dropna() <= end).all()


def test_timestamps_are_in_causal_order(demo):
    responded = demo.dropna(subset=["first_response_at"])
    assert (responded["first_response_at"] > responded["created_at"]).all()
    resolved = demo.dropna(subset=["resolved_at"])
    assert (resolved["resolved_at"] > resolved["first_response_at"]).all()


def test_some_tickets_still_open(demo):
    open_ = demo[demo["resolved_at"].isna()]
    assert 0 < len(open_) < len(demo) * 0.2
    assert set(open_["status"]) <= {"Open", "In Progress", "Waiting for customer"}


def test_arrivals_follow_the_working_week(demo):
    local = demo["created_at"].dt.tz_convert("Europe/London")
    by_day = local.dt.weekday.value_counts()
    assert by_day[0] > by_day[2] > by_day[5]  # Monday spike, quiet Saturday
    business = local.dt.hour.between(8, 17).mean()
    assert business > 0.7


def test_metrics_recover_every_planted_outcome(demo, loaded):
    cfg = Config(timezone="Europe/London")
    evaluated = sla.evaluate(loaded, cfg, pd.Timestamp(END, tz="Europe/London"))
    truth = demo.set_index("ticket_id")
    evaluated = evaluated.set_index("id")

    resp_mismatch = (evaluated["response_status"] != truth["true_response_status"]).sum()
    res_mismatch = (evaluated["resolve_status"] != truth["true_resolve_status"]).sum()
    assert resp_mismatch == 0
    assert res_mismatch == 0


def test_breach_rates_roughly_match_generator_settings(loaded):
    result = analyze(loaded, Config(), as_of=pd.Timestamp(END, tz="Europe/London"))
    # Planted rates are 5-18% by priority; overall should land in that band.
    assert 0.05 < result.response.rate < 0.15
    assert 0.05 < result.resolve.rate < 0.15
    assert result.warnings == []


def test_rejects_config_missing_a_priority():
    cfg = Config(sla={"P1": Config().sla["P1"]})
    with pytest.raises(ValueError, match="P2, P3, P4"):
        generate(10, end=END, config=cfg)


@pytest.mark.parametrize("kwargs", [{"n": 0}, {"n": 5, "days": 0}])
def test_rejects_bad_sizes(kwargs):
    with pytest.raises(ValueError):
        generate(end=END, **kwargs)
