# Proposal

## Why

An awarded match is `COMPLETED` with `awarded: true`, whether it was played to the end, abandoned midway or never kicked off. A client can't tell CF Reus's 21 forfeited matches in Segunda División 2018-19 from Union Berlin v Bochum 2024-25, which was played to the end and then awarded. openfootball's `[awarded]` tag doesn't say either, so the answer has to be curated.

## What Changes

- **New match field `played`:** `FULL` (played to the end), `PARTIAL` (abandoned) or `NONE` (never kicked off). Every `COMPLETED` match that isn't awarded is `FULL`. An awarded match takes the curated value. It's null for matches that aren't `COMPLETED`, and for an awarded match nobody has curated yet. Available in REST and GraphQL. The change only adds a field, so nothing breaks.
- **New seed `seeds/awarded.yaml`:** one entry per awarded match, with `played`, a reason and a source, as `standings.yaml` does for awarded winners. A team-wide entry covers a club's remaining fixtures after it was expelled (Reus, from 19 January 2019).
- **Sync warns** about an awarded match the seed doesn't cover, stores `played: null`, and carries on. This way a new `[awarded]` tag upstream doesn't stop the scheduled run.
- **The 42 awarded matches in today's sources**, as first drafted below. Each one is confirmed against an official source before it goes in the seed (tasks 2.x). This draft is a starting point and hasn't been checked yet:

| Match                                                     | Draft         |
| --------------------------------------------------------- | ------------- |
| Segunda División 2018-19: Reus's 21 second-half games     | `NONE`        |
| EFL Cup 2020-21: Leyton Orient v Tottenham                | `NONE`        |
| Europa League 2020-21: Villarreal v Qarabağ               | `NONE`        |
| Conference League 2021-22: Tottenham v Rennes             | `NONE`        |
| Coppa Italia 2020-21: Reggiana v Monopoli                 | `NONE`        |
| Coppa Italia 2020-21: Brescia v Trapani                   | `NONE`        |
| Ligue 1 2016-17: Bastia v Lyon                            | `PARTIAL`     |
| Ligue 1 2024-25: Montpellier v Saint-Étienne              | `PARTIAL`     |
| Copa Libertadores 2015: Boca Juniors v River Plate        | `PARTIAL`     |
| Copa Libertadores 2025: Colo-Colo v Fortaleza             | `PARTIAL`     |
| Bundesliga 2024-25: Union Berlin v Bochum                 | `FULL`        |
| Serie A 2016-17: Sassuolo v Pescara                       | `FULL`        |
| Serie A 2020-21: Verona v Roma                            | `FULL`        |
| DFB-Pokal 2021-22: Preußen Münster v Wolfsburg            | `FULL`        |
| Coppa Italia 2020-21: Roma v Spezia                       | `FULL`        |
| Copa del Rey 2023-24: Arosa v Granada                     | to be checked |
| Coppa Italia 2020-21: Empoli v Brescia                    | to be checked |
| Coupe de France 2024-25: 3 matches                        | to be checked |
| Copa Libertadores 2017: Lanús v Chapecoense               | to be checked |
| Copa Libertadores 2026: Independiente Medellín v Flamengo | to be checked |

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `matches`: Match record. A `COMPLETED` match says whether it was played in full, in part or not at all. Awarded matches are covered by a curated seed.

## Impact

- **Database:** a nullable `played` column on `match`, with an Alembic migration.
- **Code:** the seed loader and its validation, sync (setting `played`, warning about awarded matches nobody has curated), REST schemas and GraphQL types, and `schema.graphql`.
- **Seeds:** the new `seeds/awarded.yaml`. The Reus entry needs Segunda División (#47) to be merged first.
- **Docs:** the README's paragraph on awarded matches.
