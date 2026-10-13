"""The generator plants outcomes, so the metrics must recover them exactly.

Timelines use business-hours calendars, waiting periods, reopens and
escalations; the metrics see them only through the exported CSV files.
"""

from pathlib import Path

import pandas as pd
import pytest

from itsm_insights import timeline
from itsm_insights.analysis import analyze
from itsm_insights.config import Config, load_config
from itsm_insights.generator import demo_config, generate, history_path, to_csv
from itsm_insights.loaders import load_history, load_tickets
from itsm_insights.metrics import sla

END = "2026-09-30T18:00"
EXAMPLE = Path(__file__).parents[1] / "examples" / "sla.yaml"


@pytest.fixture(scope="module")
def demo():
    return generate(3000, end=END, days=60, seed=7, truth=True)


@pytest.fixture(scope="module")
def loaded(demo, tmp_path_factory):
    folder = tmp_path_factory.mktemp("demo")
    to_csv(demo.tickets, folder / "demo.csv")
    to_csv(demo.history, folder / "demo_history.csv")
    cfg = demo_config()
    return (
        load_tickets(folder / "demo.csv", cfg),
        load_history(folder / "demo_history.csv", cfg),
    )


AS_OF = pd.Timestamp(END, tz="Europe/London")


def test_example_config_matches_the_demo_policy():
    assert load_config(EXAMPLE) == demo_config()


def test_deterministic_for_a_seed():
    a = generate(200, end=END, seed=1)
    b = generate(200, end=END, seed=1)
    c = generate(200, end=END, seed=2)
    pd.testing.assert_frame_equal(a.tickets, b.tickets)
    pd.testing.assert_frame_equal(a.history, b.history)
    assert not a.tickets.equals(c.tickets)


def test_schema_and_ordering(demo):
    t = demo.tickets
    assert list(t.columns[:8]) == [
        "ticket_id", "created_at", "priority", "category", "assignee_group", "status",
        "first_response_at", "resolved_at",
    ]  # fmt: skip
    assert t["ticket_id"].is_unique
    assert t["created_at"].is_monotonic_increasing
    assert list(demo.history.columns) == ["ticket_id", "changed_at", "field", "value"]


def test_nothing_after_the_export_time(demo):
    assert (demo.tickets["created_at"] < AS_OF).all()
    assert (demo.tickets["resolved_at"].dropna() <= AS_OF).all()
    assert (demo.history["changed_at"] <= AS_OF).all()


def test_timestamps_are_in_causal_order(demo):
    t = demo.tickets
    responded = t.dropna(subset=["first_response_at"])
    assert (responded["first_response_at"] > responded["created_at"]).all()
    resolved = t.dropna(subset=["resolved_at"])
    assert (resolved["resolved_at"] > resolved["first_response_at"]).all()
    first_event = demo.history.groupby("ticket_id")["changed_at"].min()
    created = t.set_index("ticket_id")["created_at"]
    assert (first_event == created[first_event.index]).all()


def test_realistic_mix(demo):
    t = demo.tickets
    assert 0 < t["resolved_at"].isna().mean() < 0.2
    assert 0.03 < t["true_reopened"].mean() < 0.1
    assert 0.15 < t["true_escalated"].mean() < 0.3
    waits = demo.history["value"].isin(["Waiting for customer", "Pending vendor"])
    assert waits.any()
    local = t["created_at"].dt.tz_convert("Europe/London")
    by_day = local.dt.weekday.value_counts()
    assert by_day[0] > by_day[2] > by_day[5]  # Monday spike, quiet Saturday


def test_metrics_recover_every_planted_sla_outcome(demo, loaded):
    tickets, history = loaded
    cfg = demo_config()
    pauses = timeline.pause_intervals(history, cfg, AS_OF)
    evaluated = sla.evaluate(tickets, cfg, AS_OF, pauses=pauses).set_index("id")
    truth = demo.tickets.set_index("ticket_id")
    for kind in ("response", "resolve"):
        mismatch = evaluated[f"{kind}_status"] != truth[f"true_{kind}_status"]
        assert mismatch.sum() == 0, truth[mismatch].head()


def test_ignoring_pauses_and_calendars_gets_it_wrong(demo, loaded):
    """The same data measured naively disagrees with the truth: the features matter."""
    tickets, _ = loaded
    naive = Config(
        timezone="Europe/London",
        sla={
            p: {"response": pol.response, "resolve": pol.resolve}
            for p, pol in demo_config().sla.items()
        },
    )
    evaluated = sla.evaluate(tickets, naive, AS_OF).set_index("id")
    truth = demo.tickets.set_index("ticket_id")
    assert (evaluated["resolve_status"] != truth["true_resolve_status"]).sum() > 50


def test_handling_facts_match_truth(demo, loaded):
    tickets, history = loaded
    facts = timeline.ticket_facts(tickets, history, demo_config())
    truth = demo.tickets.set_index("ticket_id")
    assert ((facts["reopens"] > 0) == truth["true_reopened"]).all()
    assert ((facts["escalations"] > 0) == truth["true_escalated"]).all()
    result = analyze(tickets, demo_config(), as_of=AS_OF, history=history).as_dict()
    resolved = truth[truth["resolved_at"].notna()]
    assert result["handling"]["fcr"]["count"] == int(resolved["true_fcr"].sum())
    assert result["handling"]["fcr"]["of"] == len(resolved)


def test_analysis_is_clean_on_demo_data(loaded):
    tickets, history = loaded
    result = analyze(tickets, demo_config(), as_of=AS_OF, history=history)
    assert result.warnings == []
    assert 0.03 < result.response.rate < 0.2
    assert 0.03 < result.resolve.rate < 0.25


def test_rejects_config_missing_a_priority():
    cfg = Config(sla={"P1": Config().sla["P1"]})
    with pytest.raises(ValueError, match="P2, P3, P4"):
        generate(10, end=END, config=cfg)


@pytest.mark.parametrize("kwargs", [{"n": 0}, {"n": 5, "days": 0}])
def test_rejects_bad_sizes(kwargs):
    with pytest.raises(ValueError):
        generate(end=END, **kwargs)


def test_history_path():
    assert history_path("out/demo.csv") == "out/demo_history.csv"
    assert history_path("demo") == "demo_history"
