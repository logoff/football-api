"""tools/verify_report.py: the summary of a `sync --verify` log."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

LOG = """\
INFO Premier League 2023-24: verified against wikipedia: VERIFIED=379 MISMATCH=1 UNCONFIRMED=0 SOURCE_BEHIND=0
WARNING Premier League 2023-24: MISMATCH Arsenal v Chelsea: stored 5–0, wikipedia 4–0
INFO Premier League 2023-24: standings checked against wikipedia: VERIFIED=19 MISMATCH=1 UNCONFIRMED=0
WARNING Premier League 2023-24: MISMATCH table Arsenal: stored pos 2, P38 W28 D5 L5 91-29 89 pts, wikipedia pos 2, P38 W28 D5 L5 90-29 89 pts
INFO FIFA World Cup 2022: verified against wikipedia: VERIFIED=64 MISMATCH=0 UNCONFIRMED=0 SOURCE_BEHIND=0 unpaired=2
WARNING La Liga 2026-27: SOURCE_BEHIND Girona v Getafe: stored -, wikipedia 1–0
"""


def _load() -> ModuleType:
    path = Path(__file__).parent.parent / "tools" / "verify_report.py"
    spec = importlib.util.spec_from_file_location("verify_report", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


vr = _load()


def test_log_totals_and_disagreements() -> None:
    report = vr.parse_log(LOG.splitlines())
    assert report.seasons == 2
    assert report.matches["Premier League"]["VERIFIED"] == 379
    assert report.matches["FIFA World Cup"]["unpaired"] == 2
    assert report.tables["Premier League"]["MISMATCH"] == 1
    assert set(report.disagreements) == {
        "Premier League 2023-24: MISMATCH Arsenal v Chelsea",
        "Premier League 2023-24: MISMATCH table Arsenal",
        "La Liga 2026-27: SOURCE_BEHIND Girona v Getafe",
    }
    assert not report.failed


def test_new_and_gone_since_the_baseline(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log = tmp_path / "sync.log"
    log.write_text(LOG, encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps({"disagreements": {"Premier League 2023-24: MISMATCH table Arsenal": "", "Serie A 2017-18: MISMATCH table SS Lazio": ""}}),
        encoding="utf-8",
    )
    summary = tmp_path / "summary.md"
    assert vr.main([str(log), "--baseline", str(baseline), "--markdown", str(summary)]) == 0
    text = summary.read_text(encoding="utf-8")
    assert "Since the baseline: 1 new, 1 gone" in text
    assert "⚠️ new: `Premier League 2023-24: MISMATCH Arsenal v Chelsea`" in text
    assert "✅ gone: `Serie A 2017-18: MISMATCH table SS Lazio`" in text
    assert "::warning title=New mismatch::Premier League 2023-24: MISMATCH Arsenal v Chelsea" in capsys.readouterr().out


def test_failed_season_fails_the_report(tmp_path: Path) -> None:
    log = tmp_path / "sync.log"
    log.write_text(LOG + "ERROR FIFA World Cup 2026: FAILED: unknown team 'Türkiye'\n", encoding="utf-8")
    out = tmp_path / "report.json"
    assert vr.main([str(log), "--json", str(out), "--markdown", str(tmp_path / "s.md")]) == 1
    assert json.loads(out.read_text(encoding="utf-8"))["failed"] == {"FIFA World Cup 2026": "unknown team 'Türkiye'"}


def test_missing_baseline_is_ignored(tmp_path: Path) -> None:
    log = tmp_path / "sync.log"
    log.write_text(LOG, encoding="utf-8")
    md = tmp_path / "s.md"
    assert vr.main([str(log), "--baseline", str(tmp_path / "none.json"), "--markdown", str(md)]) == 0
    assert "Since the baseline" not in md.read_text(encoding="utf-8")
