import json
from pathlib import Path

from typer.testing import CliRunner

from itsm_insights import __version__
from itsm_insights.cli import app

runner = CliRunner()
EXAMPLE = Path(__file__).parents[1] / "examples" / "sla.yaml"


def make_demo(tmp_path: Path) -> Path:
    out = tmp_path / "demo.csv"
    result = runner.invoke(
        app, ["generate-demo", "--tickets", "300", "--end", "2026-09-30T18:00", "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert "Wrote 300 synthetic tickets" in result.output
    return out


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_generate_then_analyze(tmp_path):
    demo = make_demo(tmp_path)
    result = runner.invoke(app, ["analyze", str(demo), "--config", str(EXAMPLE)])
    assert result.exit_code == 0, result.output
    assert "Response SLA breached" in result.output
    assert "P90" in result.output


def test_analyze_json(tmp_path):
    demo = make_demo(tmp_path)
    result = runner.invoke(app, ["analyze", str(demo), "--json", "--as-of", "2026-10-01T00:00Z"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["tickets"]["total"] == 300
    assert data["as_of"].startswith("2026-10-01T00:00:00")
    assert set(data["sla"]["by_priority"]) == {"P1", "P2", "P3", "P4"}
    assert 0 <= data["sla"]["resolve"]["breach_rate"] <= 1


def test_generated_csv_has_no_truth_columns_by_default(tmp_path):
    header = make_demo(tmp_path).read_text(encoding="utf-8").splitlines()[0]
    assert "true_" not in header


def test_friendly_error_for_bad_input(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("foo,bar\n1,2\n", encoding="utf-8")
    result = runner.invoke(app, ["analyze", str(bad)])
    assert result.exit_code == 1
    assert "missing required columns" in result.output
    assert "Traceback" not in result.output


def test_friendly_error_for_bad_as_of(tmp_path):
    demo = make_demo(tmp_path)
    result = runner.invoke(app, ["analyze", str(demo), "--as-of", "yesterday-ish"])
    assert result.exit_code == 1
    assert "not a valid timestamp" in result.output
