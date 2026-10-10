"""Draft `seeds/teams.yaml` from the source files plus Wikidata lookups.

Team identity is curated by hand (design.md, "Teams — curated seed file"). This tool
only produces the first draft: it collects every team string the in-scope sources use,
proposes a Wikidata QID for each (a men's football club or national team, best search
rank first), groups strings that share a QID, and marks anything it could not settle
with `# REVIEW`. Review the output before committing it.

Searches run inside SPARQL (`wikibase:mwapi`), one query per batch of names, because
the Wikidata search API rate-limits per-name lookups to a crawl.

    uv run python tools/propose_teams.py [--out seeds/teams.yaml]
"""

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import httpx

from football_api.domain.enums import TeamKind
from football_api.infra.settings import get_settings
from football_api.ingestion.openfootball.squads import parse_more_squads, parse_per_team_squad
from football_api.ingestion.openfootball.text_parser import parse_file
from football_api.ingestion.seeds import load_competitions

USER_AGENT = "football-api/0.1 (self-hosted; openfootball ingest tooling)"
BATCH = 20
TYPES = {
    TeamKind.CLUB: "wd:Q476028 wd:Q15944511 wd:Q103229495",
    TeamKind.NATIONAL: "wd:Q6979593 wd:Q135408445",
}
EXCLUDE_RE = re.compile(r"women|under-|\bu-?\d\d\b|youth|futsal|beach|reserve|academy|olympic", re.IGNORECASE)
SECOND_TEAM_RE = re.compile(r"\s(?:[BC]|II)$")
# openfootball's 3-letter country suffixes → ISO 3166-1 alpha-2 (Wikidata P297).
FIFA_TO_ISO = {
    "ARG": "AR", "ARM": "AM", "AUT": "AT", "AZE": "AZ", "BEL": "BE", "BIH": "BA", "BLR": "BY", "BOL": "BO",
    "BRA": "BR", "BUL": "BG", "CHI": "CL", "COL": "CO", "CRO": "HR", "CYP": "CY", "CZE": "CZ", "DEN": "DK",
    "ECU": "EC", "EGY": "EG", "ENG": "GB", "ESP": "ES", "FIN": "FI", "FRA": "FR", "GER": "DE", "GRE": "GR",
    "HUN": "HU", "IRL": "IE", "ISL": "IS", "ISR": "IL", "ITA": "IT", "JPN": "JP", "KAZ": "KZ", "KOR": "KR",
    "KSA": "SA", "LVA": "LV", "MAR": "MA", "MCO": "MC", "MDA": "MD", "MEX": "MX", "NED": "NL", "NIR": "GB",
    "NOR": "NO", "NZL": "NZ", "PAR": "PY", "PER": "PE", "POL": "PL", "POR": "PT", "ROU": "RO", "RSA": "ZA",
    "SCO": "GB", "SRB": "RS", "SUI": "CH", "SVK": "SK", "SVN": "SI", "SWE": "SE", "TUN": "TN", "TUR": "TR",
    "UAE": "AE", "UKR": "UA", "URU": "UY", "USA": "US", "VEN": "VE", "WAL": "GB",
}
UK_SUBDIVISIONS = {"ENG": "GB-ENG", "SCO": "GB-SCT", "WAL": "GB-WLS", "NIR": "GB-NIR"}
UK_NATIONAL = {"England": "GB-ENG", "Scotland": "GB-SCT", "Wales": "GB-WLS", "Northern Ireland": "GB-NIR"}
AFFIXES = re.compile(
    r"^(?:FC|CF|AC|SC|AFC|CD|CA|SL|RC|RCD|SSC|SS|US|ACF|AS|SV|VfB|VfL|TSG|BSC|GNK|ŠK|FK|NK|KV|KRC|HNK|SK|PFC|CR|SE|EC|CDC|CSD)\s+"
    r"|\s+(?:FC|CF|AC|SC|AFC|F\.C\.|C\.F\.|SAD|1\d{3}|\d{2})$"
)
SUFFIX_RE = re.compile(r"\s*\(([A-Z]{3})\)$")


@dataclass
class Group:
    kind: TeamKind
    strings: set[str] = field(default_factory=lambda: set[str]())
    suffix_codes: set[str] = field(default_factory=lambda: set[str]())
    league_countries: set[str] = field(default_factory=lambda: set[str]())
    qid: str | None = None
    label: str = ""
    iso: str | None = None
    review: list[str] = field(default_factory=lambda: list[str]())


@dataclass(frozen=True)
class Candidate:
    rank: tuple[int, int]
    qid: str
    label: str
    description: str
    iso: str | None


def collect(sources: Path) -> dict[str, Group]:
    """Group source strings by base name (country suffix removed)."""
    groups: dict[str, Group] = {}
    for comp in load_competitions():
        names: set[str] = set()
        for season in comp.seasons:
            for m in parse_file(sources / season.file, start_year=season.start_year, display_path=season.file):
                names |= {m.home, m.away}
            if season.json_file and (sources / season.json_file).exists():
                data = json.loads((sources / season.json_file).read_text(encoding="utf-8"))
                for m in cast(list[dict[str, str]], data["matches"]):
                    names |= {m["team1"], m["team2"]}
            if season.squads:
                for pattern in season.squads.files:
                    for path in sorted(sources.glob(pattern)):
                        text = path.read_text(encoding="utf-8")
                        squad = parse_more_squads(text) if season.squads.style == "more" else parse_per_team_squad(text)
                        names |= {p.team for p in squad}
        for name in names:
            base = SUFFIX_RE.sub("", name)
            group = groups.setdefault(base, Group(kind=comp.team_kind))
            group.strings.add(name)
            if m := SUFFIX_RE.search(name):
                group.suffix_codes.add(m.group(1))
            if comp.country:
                group.league_countries.add(comp.country)
    return groups


def search_terms(base: str, kind: TeamKind) -> list[str]:
    if kind is TeamKind.NATIONAL:
        return [f"{base} national football team"]
    simplified = AFFIXES.sub("", AFFIXES.sub("", base)).strip()
    return [base] if not simplified or simplified == base else [base, simplified]


def sparql_search(client: httpx.Client, terms: list[str], kind: TeamKind) -> list[dict[str, str]]:
    values = " ".join(json.dumps(t, ensure_ascii=False) for t in terms)
    query = f"""
SELECT ?term ?item ?ordinal ?itemLabel ?desc ?iso WHERE {{
  VALUES ?term {{ {values} }}
  SERVICE wikibase:mwapi {{
    bd:serviceParam wikibase:endpoint "www.wikidata.org"; wikibase:api "EntitySearch";
                    mwapi:search ?term; mwapi:language "en"; mwapi:limit "7" .
    ?item wikibase:apiOutputItem mwapi:item .
    ?ordinal wikibase:apiOrdinal true .
  }}
  VALUES ?type {{ {TYPES[kind]} }}
  ?item wdt:P31 ?type .
  OPTIONAL {{ ?item schema:description ?desc FILTER(lang(?desc) = "en") }}
  OPTIONAL {{ ?item wdt:P17/wdt:P297 ?iso }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}"""
    for _ in range(10):
        resp = client.post(
            get_settings().wikidata_endpoint,
            data={"query": query},
            headers={"Accept": "application/sparql-results+json"},
        )
        if resp.status_code == 429 or resp.status_code >= 500:
            delay = int(resp.headers.get("Retry-After", "30"))
            print(f"  sparql {resp.status_code}; retrying in {delay}s", file=sys.stderr)
            time.sleep(delay)
            continue
        resp.raise_for_status()
        rows = cast(list[dict[str, dict[str, str]]], resp.json()["results"]["bindings"])
        return [{k: v["value"] for k, v in row.items()} for row in rows]
    raise RuntimeError("Wikidata SPARQL kept refusing requests")


def propose(groups: dict[str, Group]) -> None:
    client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=120)
    for kind in TeamKind:
        bases = sorted(b for b, g in groups.items() if g.kind is kind)
        term_owner: dict[str, tuple[str, int]] = {}
        for base in bases:
            for i, term in enumerate(search_terms(base, kind)):
                term_owner.setdefault(term, (base, i))
        terms = list(term_owner)
        candidates: dict[str, list[Candidate]] = defaultdict(list)
        for start in range(0, len(terms), BATCH):
            batch = terms[start : start + BATCH]
            print(f"{kind.value}: terms {start + 1}-{start + len(batch)} of {len(terms)}", file=sys.stderr)
            for row in sparql_search(client, batch, kind):
                base, term_index = term_owner[row["term"]]
                candidates[base].append(
                    Candidate(
                        rank=(term_index, int(row["ordinal"])),
                        qid=row["item"].rsplit("/", 1)[-1],
                        label=row.get("itemLabel", ""),
                        description=row.get("desc", ""),
                        iso=row.get("iso"),
                    )
                )
        for base in bases:
            group = groups[base]
            expected = {FIFA_TO_ISO[c] for c in group.suffix_codes if c in FIFA_TO_ISO}
            expected |= {c.split("-")[0] for c in group.league_countries}
            ranked = sorted(
                (
                    c
                    for c in candidates[base]
                    if not EXCLUDE_RE.search(f"{c.label} {c.description}")
                    and not SECOND_TEAM_RE.search(c.label)
                    and (not expected or c.iso is None or c.iso in expected)
                ),
                key=lambda c: c.rank,
            )
            unique = list(dict.fromkeys(c.qid for c in ranked))
            if not unique:
                group.review.append("no Wikidata match")
                continue
            best = next(c for c in ranked if c.qid == unique[0])
            group.qid, group.label, group.iso = best.qid, best.label, best.iso
            if len(unique) > 1:
                group.review.append(f"other candidates: {', '.join(unique[1:4])}")


def _clean_label(label: str, kind: TeamKind) -> str:
    if kind is TeamKind.NATIONAL:
        return re.sub(r"\s+(?:men's\s+)?national (?:association )?football team$", "", label)
    return re.sub(r"\s+(?:F\.C\.|FC|A\.F\.C\.)$", "", label)


def render(groups: dict[str, Group]) -> str:
    by_qid: dict[str, list[tuple[str, Group]]] = defaultdict(list)
    unresolved: list[tuple[str, Group]] = []
    for base, group in groups.items():
        (by_qid[group.qid] if group.qid else unresolved).append((base, group))

    entries: list[tuple[str, str]] = []

    def emit(name: str, kind: TeamKind, country: str | None, qid: str | None, strings: set[str], notes: list[str]) -> None:
        head = f"- name: {json.dumps(name, ensure_ascii=False)}" + (f"  # REVIEW: {'; '.join(notes)}" if notes else "")
        lines = [
            head,
            f"  kind: {kind.value}",
            f'  country: {json.dumps(country) if country else "null"}',
            f"  wikidata: {qid or 'null'}",
            "  openfootball:",
            *[f"    - {json.dumps(s, ensure_ascii=False)}" for s in sorted(strings)],
        ]
        entries.append((name.casefold(), "\n".join(lines)))

    for qid, members in by_qid.items():
        first = members[0][1]
        kind = first.kind
        name = _clean_label(first.label, kind) or members[0][0]
        suffixes = {c for _, g in members for c in g.suffix_codes}
        leagues = {c for _, g in members for c in g.league_countries}
        uk = sorted(UK_SUBDIVISIONS[c] for c in suffixes if c in UK_SUBDIVISIONS)
        if kind is TeamKind.NATIONAL and name in UK_NATIONAL:
            country = UK_NATIONAL[name]
        elif uk:
            country = uk[0]
        elif len(leagues) == 1:
            country = next(iter(leagues))
        else:
            country = first.iso
        notes = [n for _, g in members for n in g.review]
        if len(members) > 1:
            notes.append(f"merged by QID: {', '.join(sorted(b for b, _ in members))}")
        emit(name, kind, country, qid, {s for _, g in members for s in g.strings}, notes)

    for base, group in unresolved:
        emit(base, group.kind, next(iter(group.league_countries), None), None, group.strings, group.review)

    header = (
        "# Canonical teams. Identity across sources is pinned here by hand (design.md,\n"
        '# "Teams — curated seed file"). Every openfootball spelling must be listed;\n'
        "# sync fails on an unknown name. Drafted by tools/propose_teams.py, then reviewed.\n\n"
    )
    return header + "\n\n".join(text for _, text in sorted(entries)) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=get_settings().seeds_dir / "teams.yaml")
    args = parser.parse_args()
    out = cast(Path, args.out)
    groups = collect(get_settings().sources_dir)
    print(f"{len(groups)} base names", file=sys.stderr)
    propose(groups)
    out.write_text(render(groups), encoding="utf-8")
    print(f"wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
