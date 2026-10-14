# Design

## Context

`[awarded]` is already recognised by the text parser (as status `COMPLETED`) and by the JSON reader (`"status": "awarded"`), but neither keeps it. The verifier compares every scored match in a reference grid. The 14 tagged matches in the seeded sources are listed in the PR. Thirteen have a decisive score that equals the awarded result. Bastia v Lyon has `0-0`.

## Goals / Non-Goals

**Goals:** keep the source's awarded marker end to end, and stop comparing a result the source doesn't fully state.

**Non-Goals:**

- Recording who a level awarded match went to. The source doesn't say, and seeds never override results.
- Distinguishing a forfeit from a disciplinary award, which neither source distinguishes.

## Decisions

### D1. A boolean, not a status or a `decided_by` value

`awarded` is a separate boolean. `status` stays `COMPLETED` and `decided_by` keeps its meaning (how play ended).

**Alternatives:**

- **`MatchStatus.AWARDED`.** Rejected. Every client that treats `COMPLETED` as "has a final result" would break.
- **`DecidedBy.AWARDED`.** Rejected, because an awarded match can also have been decided on penalties before the award (for example a cup tie later forfeited for an ineligible player).

### D2. Level awarded matches are not compared

The verifier treats an awarded match whose stored score is level like a match with no stored score: it gets no status, and an existing status row is deleted. Decisive awarded scores are compared normally.

**Alternative:** a new `AWARDED` verification status. Rejected, because `awarded` on the match already says it, and a status implies a comparison that didn't happen.

### D3. Parser carries the flag

`ParsedMatch.awarded` is set by both readers. `is_current` (JSON vs text) compares it too, so a mirror that loses the tag isn't preferred.

## Source coverage

**Tagged matches.** The 14 tagged matches after a full local sync:

| Competition     | Season  | Match                           | Score |
| --------------- | ------- | ------------------------------- | ----- |
| Bundesliga      | 2024-25 | 1. FC Union Berlin v VfL Bochum | 0–2   |
| Serie A         | 2016-17 | Sassuolo v Pescara              | 0–3   |
| Serie A         | 2020-21 | Hellas Verona v AS Roma         | 3–0   |
| Ligue 1         | 2016-17 | SC Bastia v Olympique Lyonnais  | 0–0   |
| Ligue 1         | 2024-25 | Montpellier v Saint-Étienne     | 0–2   |
| Copa del Rey    | 2023-24 | Arosa SC v Granada CF           | 3–0   |
| DFB-Pokal       | 2021-22 | Preußen Münster v VfL Wolfsburg | 2–0   |
| Coppa Italia    | 2020-21 | Reggiana v Monopoli             | 0–3   |
| Coppa Italia    | 2020-21 | Brescia v Trapani               | 3–0   |
| Coppa Italia    | 2020-21 | Empoli v Brescia                | 3–0   |
| Coppa Italia    | 2020-21 | AS Roma v Spezia                | 0–3   |
| Coupe de France | 2024-25 | Étoile Maritime v USSA Vertou   | 0–3   |
| Coupe de France | 2024-25 | FC Marmande v Vierzon           | 3–0   |
| Coupe de France | 2024-25 | Tours FC v FC Lorient           | 0–3   |

**Verified run of the five leagues** (empty database): 32,808 `VERIFIED`, 47 `SOURCE_BEHIND` (2026-27) and no `MISMATCH`. Bastia v Lyon has no status, and the four league matches with decisive awarded scores are `VERIFIED`.

## Risks / Trade-offs

- **[Trade-off] Bastia v Lyon stays 0–0 with no visible winner** apart from `awarded`. → This is what the source and the LFP record hold. A future source with an explicit winner would be a separate change.
- **[Risk] Sources without the tag.** A forfeit written as a plain score stays an ordinary result. → Nothing to detect it from. This is accepted.

## Migration Plan

One Alembic revision adds `match.awarded BOOLEAN NOT NULL DEFAULT false`. The next sync sets it from the sources. The downgrade drops the column.
