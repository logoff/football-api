# Design

## Context

`resolve_scorer` resolves goals, line-ups, substitutions and cards against a team-season's squad. It first tries an exact match, case- and accent-insensitive. Then it tries a surname-aligned short form (`Koulibaly` for `Kalidou Koulibaly`), and in both cases only accepts a single candidate.

## Decisions

### D1. Every published squad file is ingested

Each World Cup, Club World Cup, Euro and Copa América season whose squad file exists names it in the seeds. The `more` and `per-team` formats already cover them, apart from D2. A squad team name that matches no seeded team fails the season's sync, as for match files; one did (`Türkiye`).

### D2. Optional shirt number

Squads before 1954 write `Jimmy DOUGLAS, GK, b. 1898/01/12`. The parser made the number optional but not its comma, so these lines never matched. The number and its comma are now optional together.

### D3. A spacing-insensitive last step

When the exact and short-form steps find no one, names are compared with spaces removed after folding. A single match resolves; several, or none, keep the name only. This is still a comparison of the same letters in the same order, so it can't confuse two different players, but it can't bridge different spellings either (`Bill` and `William Slater`, `Vladica` and `Vladimir Popović`). Those stay names only, by design.

## Risks / Trade-offs

- **[Risk] Two squad members differ only in spacing.** → Then neither resolves, the same as any ambiguous name.
