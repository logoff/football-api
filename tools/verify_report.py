"""Summarise a `python -m football_api.sync --verify` log, optionally against a baseline report.

Usage: python tools/verify_report.py SYNC_LOG [--baseline BASELINE_JSON] [--json OUT_JSON] [--markdown OUT_MD]

Reads the log the sync writes, and writes:
- a JSON report (totals per competition, every disagreement, failed seasons) to keep as a baseline;
- a Markdown summary, with what is new and gone since the baseline when one is given.

Exits 1 when the log reports failed seasons; disagreements alone never fail it, since sources
change independently of the code.
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

# `<competition> <season>: verified against wikipedia: VERIFIED=… unpaired=…`
_MATCHES = re.compile(r"^INFO (?P<label>.+?): verified against wikipedia: (?P<counts>.*)$")
_TABLES = re.compile(r"^INFO (?P<label>.+?): standings checked against wikipedia: (?P<counts>.*)$")
# `<competition> <season>: MISMATCH <home> v <away>: stored …` and `…: MISMATCH table <team>: stored …`
_DISAGREEMENT = re.compile(r"^WARNING (?P<key>(?P<label>.+?): (?:MISMATCH|SOURCE_BEHIND) .+?): stored (?P<detail>.*)$")
_FAILED = re.compile(r"^ERROR (?P<label>.+?): FAILED: (?P<error>.*)$")
_SEASON = re.compile(r"^(?P<competition>.+) (?P<season>\d{4}(?:-\d{2})?)$")


@dataclass
class Report:
    matches: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    tables: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    disagreements: dict[str, str] = field(default_factory=dict[str, str])
    failed: dict[str, str] = field(default_factory=dict[str, str])
    seasons: int = 0

    def to_json(self) -> dict[str, object]:
        return {
            "seasons": self.seasons,
            "matches": {c: dict(v) for c, v in sorted(self.matches.items())},
            "tables": {c: dict(v) for c, v in sorted(self.tables.items())},
            "disagreements": dict(sorted(self.disagreements.items())),
            "failed": dict(sorted(self.failed.items())),
        }


def competition_of(label: str) -> str:
    m = _SEASON.match(label)
    return m["competition"] if m else label


def parse_log(lines: list[str]) -> Report:
    report = Report()
    for line in lines:
        line = line.rstrip("\n")
        if m := _MATCHES.match(line):
            report.seasons += 1
            for key, value in re.findall(r"(\w+)=(\d+)", m["counts"]):
                report.matches[competition_of(m["label"])][key] += int(value)
        elif m := _TABLES.match(line):
            for key, value in re.findall(r"(\w+)=(\d+)", m["counts"]):
                report.tables[competition_of(m["label"])][key] += int(value)
        elif m := _DISAGREEMENT.match(line):
            report.disagreements[m["key"]] = m["detail"]
        elif m := _FAILED.match(line):
            report.failed[m["label"]] = m["error"]
    return report


def baseline_disagreements(baseline: dict[str, object]) -> set[str]:
    keys = baseline.get("disagreements", {})
    return {str(k) for k in cast(dict[str, object], keys)} if isinstance(keys, dict) else set()


def markdown(report: Report, baseline: dict[str, object] | None) -> str:
    out = ["## Full sync and verification", ""]
    if report.failed:
        out += [f"**{len(report.failed)} season(s) failed:**", ""]
        out += [f"- `{label}`: {error}" for label, error in sorted(report.failed.items())] + [""]
    out += [f"{report.seasons} seasons verified.", ""]
    out += ["| Competition | Matches verified | Mismatch | Unconfirmed | Behind | Unpaired | Table rows verified | Table mismatch | Table unconfirmed |"]
    out += ["| --- | --: | --: | --: | --: | --: | --: | --: | --: |"]
    for comp in sorted(set(report.matches) | set(report.tables)):
        m, t = report.matches.get(comp, Counter[str]()), report.tables.get(comp, Counter[str]())
        out.append(
            f"| {comp} | {m['VERIFIED']} | {m['MISMATCH']} | {m['UNCONFIRMED']} | {m['SOURCE_BEHIND']} | {m['unpaired']} "
            f"| {t['VERIFIED']} | {t['MISMATCH']} | {t['UNCONFIRMED']} |"
        )
    out.append("")
    mismatches = {k: v for k, v in report.disagreements.items() if ": MISMATCH " in k}
    if baseline is not None:
        before = {k for k in baseline_disagreements(baseline) if ": MISMATCH " in k}
        new, gone = sorted(set(mismatches) - before), sorted(before - set(mismatches))
        out += [f"### Since the baseline: {len(new)} new, {len(gone)} gone", ""]
        out += [f"- ⚠️ new: `{k}`: stored {mismatches[k]}" for k in new]
        out += [f"- ✅ gone: `{k}`" for k in gone]
        out.append("")
    out += [f"<details><summary>All {len(mismatches)} mismatches</summary>", ""]
    out += [f"- `{k}`: stored {v}" for k, v in sorted(mismatches.items())]
    out += ["", "</details>", ""]
    return "\n".join(out)


def new_mismatches(report: Report, baseline: dict[str, object]) -> list[str]:
    before = baseline_disagreements(baseline)
    return sorted(k for k in report.disagreements if ": MISMATCH " in k and k not in before)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarise a sync --verify log, optionally against a baseline report.")
    parser.add_argument("log", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args(argv)

    report = parse_log(args.log.read_text(encoding="utf-8", errors="replace").splitlines())
    baseline = json.loads(args.baseline.read_text(encoding="utf-8")) if args.baseline and args.baseline.exists() else None
    if args.json:
        args.json.write_text(json.dumps(report.to_json(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    text = markdown(report, baseline)
    if args.markdown:
        args.markdown.write_text(text, encoding="utf-8")
    else:
        print(text)
    if baseline is not None:
        for key in new_mismatches(report, baseline):  # GitHub shows these as annotations on the run
            print(f"::warning title=New mismatch::{key}")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
