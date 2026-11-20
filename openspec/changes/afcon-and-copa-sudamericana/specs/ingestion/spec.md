## MODIFIED Requirements

### Requirement: Stage from section headings

Each match box SHALL take its stage, and its group or round number where there is one, from the section heading above it: preliminary round, numbered round, group, quarter-finals, semi-finals, third place (`Third place play-off`, `Third-place match`), final (`Final`, `Finals`), and their variants. A replay or play-off of a tie SHALL keep the stage of that tie. A heading that only wraps rounds (`Knockout phase`, `Final phase`, `Final stages`, `Tournament phase`, `Qualifying phase`) SHALL name no stage, so the round under it decides. A box under a heading that maps to no stage SHALL fail the season.

#### Scenario: Numbered rounds and groups

- **GIVEN** boxes under `First round`, `Group B` and `Quarter-finals`
- **WHEN** they are read
- **THEN** their stages are `ROUND` with matchday 1, `GROUP` with group `B`, and `QF`

#### Scenario: Unknown heading

- **GIVEN** a box under the heading `Trivia`
- **WHEN** the season is synced
- **THEN** the season fails with an error naming the page, revision and heading

#### Scenario: Round under a phase wrapper

- **GIVEN** the 1999–2000 UEFA Cup box under `Final phase / Third round`
- **WHEN** it is read
- **THEN** its stage is `ROUND` with matchday 3, not `FINAL`

#### Scenario: Two-legged final

- **GIVEN** the 1975 Copa América boxes under `Knockout stage / Finals`: two legs and a play-off
- **WHEN** they are read
- **THEN** all three have stage `FINAL`

#### Scenario: Third-place match

- **GIVEN** the 1993 Copa América box under `Knockout stage / Third-place match`
- **WHEN** it is read
- **THEN** its stage is `THIRD_PLACE`

#### Scenario: Round under the final stages

- **GIVEN** the 2025 Copa Sudamericana boxes under `Final stages / Knockout round play-offs`
- **WHEN** they are read
- **THEN** their stage is `PLAYOFF`, not `FINAL`
