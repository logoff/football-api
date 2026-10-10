"""Wikidata SPARQL adapter: confirms that seeded QIDs still exist."""

import httpx

USER_AGENT = "football-api/0.1 (self-hosted; openfootball ingest)"
BATCH = 200


class WikidataUnavailable(Exception):
    pass


async def verify_qids(qids: list[str], *, endpoint: str, timeout: float = 30.0) -> set[str]:
    """Return the subset of `qids` that exist as items (not deleted, not redirects)."""
    found: set[str] = set()
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=timeout) as client:
        for i in range(0, len(qids), BATCH):
            values = " ".join(f"wd:{q}" for q in qids[i : i + BATCH])
            query = f"SELECT ?item WHERE {{ VALUES ?item {{ {values} }} ?item wikibase:sitelinks ?n . }}"
            try:
                resp = await client.get(
                    endpoint, params={"query": query}, headers={"Accept": "application/sparql-results+json"}
                )
            except httpx.TransportError as exc:
                raise WikidataUnavailable(str(exc) or type(exc).__name__) from exc
            if resp.status_code >= 500 or resp.status_code == 429:
                raise WikidataUnavailable(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            for row in resp.json()["results"]["bindings"]:
                found.add(str(row["item"]["value"]).rsplit("/", 1)[-1])
    return found
