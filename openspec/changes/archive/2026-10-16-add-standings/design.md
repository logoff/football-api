# Design

## Context

Matches carry a stage (`LEAGUE`, `GROUP`, …), the source's round label, the score at the end of play, how the match was decided, and whether it was awarded. Domestic league matches are all `LEAGUE`. Tournament group matches are `GROUP`, and the UEFA league phases (2024-25 onward) are `LEAGUE`.

Group names live only in round labels, and in many spellings: `Group A`, `Gruppe A`, `Group 1`, `First stage / Group A`, `First Stage, Group A`, `Group Matches / Group 1`, `Group Stage / Group A`, `Second Round / Group B`. Some seasons don't name groups at all (`Group, Matchday 1`).

## Goals / Non-Goals

**Goals:**

- Correct final and in-progress tables for every league season and tournament group in the database, with the official ranking rules of each competition and era.
- Point deductions and non-sporting tie decisions are explicit, sourced and reviewable.

**Non-Goals:**

- Fair-play points, disciplinary records and coefficients (no card data). Ties these would decide are flagged and settled by a curated order.
- Ranking third-placed teams across groups (Euro 2016+, World Cup 2026). That's a possible follow-up.
- Storing tables.

## Decisions

### D1. Computed on request

A table is a fold over at most about 400 matches, so the endpoint computes it from the stored matches on each request. There's no table storage to keep in sync with relabelled, removed or corrected matches.

**Alternative:** materialised standings, refreshed by the sync. Rejected: a second copy of the truth for no measurable gain.

### D2. Which matches count

A match counts when it's `COMPLETED` with a score and its stage is `LEAGUE` or `GROUP`.

- **Awarded matches** count with the score the source records.
- **Extra time and penalties** don't happen in table matches, so the score at the end of play is the result.
- **`as_of`** (a date) keeps the matches whose kickoff date, in the season's time zone, is on or before it.

### D3. Tables and groups

- **One table per (phase, group).**
- **Phase:** a round label starting `Second Round` is phase 2, and everything else is phase 1. This is how the World Cup's 1974–1982 second rounds are stored.
- **Group:** the group name is the letter or number after `Group` or `Gruppe` in the label.
- **Unnamed groups:** when a phase has unnamed matches, its groups are the connected components of the "played each other" graph, with no name. They're ordered by their earliest kickoff, then by team name.
- **Leagues and league phases** are one table with no group.

### D4. Ranking rules from the seeds

Each competition in `competitions.yaml` gets a `standings` block, a list of eras:

```yaml
standings:
  - from: 1930
    points: {win: 2, draw: 1, loss: 0}
    tiebreakers: [goal_difference, goals_for]
  - from: 1994
    points: {win: 3, draw: 1, loss: 0}
    tiebreakers: [goal_difference, goals_for, h2h_points, h2h_goal_difference, h2h_goals_for]
```

`from` is a season's start year, so it reads the same for `1992-93` and `2026`. The era applying to a season is the last one whose `from` is at or before the season's start year.

**Criteria:**

| Criterion                                                                  | Meaning                                                                                      |
| -------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `goal_difference`, `goals_for`                                             | Overall, in the table's matches                                                              |
| `goal_ratio`                                                               | Goal average: goals for ÷ goals against                                                      |
| `wins`, `away_wins`, `away_goals_for`                                      | Overall, in the table's matches                                                              |
| `h2h_points`, `h2h_goal_difference`, `h2h_goals_for`, `h2h_away_goals_for` | In the matches among the teams still tied                                                    |
| `h2h_reapply`                                                              | Restart the head-to-head criteria for any subset that is still tied but smaller (UEFA style) |
| `opponents_points`, `opponents_goal_difference`, `opponents_goals_for`     | Sums over each team's opponents (UEFA league phase)                                          |

**Applying them:**

- Criteria apply in order to each set of teams level on points, splitting it into ordered subsets.
- Head-to-head criteria are always computed among the teams of the current tied subset.
- Whatever is still tied after the last criterion is a **tie**: the rows get `tied: true` and keep a stable order (team name), unless a curated order applies (D5).

A season can override the ranking with `ranking: points_per_game`. That season's tie-breakers then apply to equal points per game.

### D5. Curated adjustments

`seeds/standings.yaml` holds two kinds of entries:

```yaml
- competition: Q9448          # Premier League
  season: "2023-24"
  team: Q5794                  # Everton (Wikidata, as in teams.yaml)
  points: -8
  reason: "Deducted 10 (reduced to 6 on appeal) and 2 for breaching profit and sustainability rules"
  source: https://www.premierleague.com/news/...

- competition: Q15804          # Serie A
  season: "2022-23"
  order: [Q…, Q…]              # final order of teams results can't separate
  reason: "Relegation play-off: Hellas Verona 3–1 Spezia"
  source: https://…
```

- **Point adjustments** apply to the final table and to `as_of` dates on or after their effective date (optional `effective`; if not given, the whole season).
- **An `order` entry** applies when its teams are exactly a set level on points: it then replaces the tie-breakers, as a play-off does (Serie A since 2022-23: Hellas Verona above Spezia in 2022-23). It also applies when its teams are exactly a set the tie-breakers leave level. Either way the rows carry `tied: true`, so clients can see the order was decided off the table.
- **Validation at load:** competitions, seasons and teams must exist, and team QIDs must be in `teams.yaml`. A mistyped entry fails the API start rather than being silently ignored.

### D6. Status

- **`final`:** the season is completed and none of the table's matches is still unplayed.
- **`provisional`:** otherwise, including whenever `as_of` falls before the last table match.

## Risks / Trade-offs

- **[Risk] A ranking rule is encoded wrongly, or an era boundary is off by a season.** → The follow-up `verify-standings` compares every final table with Wikipedia's standings, as match verification does for scores.
- **[Risk] A deduction is missing.** → The same check flags points that disagree with Wikipedia. Each fix is a reviewed seed entry with a source.
- **[Trade-off] Unnamed groups have no name.** Clients get the group's teams and matches, but not "Group C". Names would need a source openfootball doesn't provide for those seasons.
