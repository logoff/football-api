# match-verification Specification

## Purpose

Checks stored match results against an independent, openly licensed reference so clients can tell which results two sources agree on, without ever changing the data or serving the reference's content.

## Requirements

### Requirement: Reference results for domestic leagues

The system SHALL use the results grid of the English Wikipedia article named by each configured domestic league season as the verification reference. A season that names no article is not verified. Reference teams SHALL be matched to stored teams only through their Wikidata QID.

#### Scenario: Grid resolved for a configured season

- **GIVEN** La Liga 2025-26 is a configured season
- **WHEN** verification runs for La Liga
- **THEN** the reference results are read from the 2025–26 La Liga article's results grid
- **AND** each grid team is identified by the Wikidata QID of the article it links to

#### Scenario: Article reached through a redirect

- **GIVEN** a season names an article title that redirects, such as `2000–01 Premier League` (redirects to `2000–01 FA Premier League`)
- **WHEN** verification runs for that season
- **THEN** the grid of the redirect target is used and its scores are compared

#### Scenario: Season without an article

- **GIVEN** a Serie A season that names no article, while the other Serie A seasons do
- **WHEN** verification runs for Serie A
- **THEN** that season is skipped without a warning and its matches have no status
- **AND** the other Serie A seasons are verified

#### Scenario: Reference team without a known QID

- **GIVEN** a grid team whose linked article has no Wikidata QID, or whose QID matches no stored team
- **WHEN** verification runs
- **THEN** that team's matches are not compared and keep or receive no status
- **AND** a warning naming the team is logged

### Requirement: Verification status per match

Each stored match with a counterpart in the reference SHALL get one status: `VERIFIED` (same home and away score, and the same shootout score when both sources have one), `MISMATCH` (both have a score and they differ), `UNCONFIRMED` (only the stored match has a score), or `SOURCE_BEHIND` (only the reference has one). Matches with no score in either source get no status. An awarded match whose stored score is level gets no status either: the source names no winner, so its score can't be compared with a reference that records the awarded result.

#### Scenario: Scores agree

- **GIVEN** a stored match Sevilla 2–1 Rayo Vallecano and a reference cell 2–1 for the same pairing
- **WHEN** verification runs
- **THEN** the match's status is `VERIFIED`

#### Scenario: Scores differ

- **GIVEN** a stored score 2–1 and a reference score 2–2 for the same pairing
- **WHEN** verification runs
- **THEN** the match's status is `MISMATCH`
- **AND** the stored score is unchanged

#### Scenario: Reference lags behind

- **GIVEN** a stored completed match whose reference cell is empty or a placeholder
- **WHEN** verification runs
- **THEN** the match's status is `UNCONFIRMED`

#### Scenario: Stored data lags behind

- **GIVEN** a stored match with no score whose reference cell has a score
- **WHEN** verification runs
- **THEN** the match's status is `SOURCE_BEHIND`

#### Scenario: Status follows the sources

- **GIVEN** a match that was `UNCONFIRMED`
- **WHEN** the reference later shows the same score and verification runs again
- **THEN** the status becomes `VERIFIED` and its check time is updated

#### Scenario: Awarded match recorded with a level score

- **GIVEN** a stored awarded match SC Bastia 0–0 Olympique Lyonnais and a reference cell 0–3
- **WHEN** verification runs
- **THEN** the match has no status, and any status it had is removed
- **AND** no disagreement is logged for it

#### Scenario: Awarded match recorded with the awarded score

- **GIVEN** a stored awarded match 1. FC Union Berlin 0–2 VfL Bochum 1848 and a reference cell 0–2
- **WHEN** verification runs
- **THEN** the match's status is `VERIFIED`

#### Scenario: Shootout scores compared

- **GIVEN** a stored cup match 1–1 decided 4–1 on penalties and a reference box 1–1 (a.e.t.) (4–2 p)
- **WHEN** verification runs
- **THEN** the match's status is `MISMATCH`

### Requirement: Reference content is never stored or served

The system SHALL NOT store, serve or change match data from the reference. Only the status, the reference's name and the time of the check SHALL be persisted, and, for deciding when to verify again, the titles and revision IDs of the reference pages read. Titles and revision IDs SHALL NOT be served.

#### Scenario: Mismatch leaves no reference data behind

- **GIVEN** a match marked `MISMATCH`
- **WHEN** a client GETs the match
- **THEN** the response contains the stored score and the verification status
- **AND** contains no score or other value taken from the reference

### Requirement: Disagreement report

Each verification run SHALL log one line per `MISMATCH` and `SOURCE_BEHIND` match (season, teams, stored and reference score) and a summary with the count of each status per season. A season that isn't verified again SHALL log the same summary from its stored statuses, marked as unchanged, and one line per stored `MISMATCH` and `SOURCE_BEHIND` match with the stored score and the date of its last check in place of the reference score.

#### Scenario: Summary after a run

- **WHEN** verification for La Liga finishes
- **THEN** the log contains, for each configured season, the number of `VERIFIED`, `MISMATCH`, `UNCONFIRMED` and `SOURCE_BEHIND` matches

#### Scenario: Mismatch is listed

- **GIVEN** a match marked `MISMATCH`
- **WHEN** verification finishes
- **THEN** the log has a line naming the season, both teams, the stored score and the reference score

#### Scenario: Mismatch in an unchanged season

- **GIVEN** a match marked `MISMATCH` in a season that isn't verified again
- **WHEN** verification finishes
- **THEN** the log has a line naming the season, both teams and the stored score, in the same format up to the stored score, and the season's summary is marked as unchanged

### Requirement: Reference unavailable

If the reference for a season can't be fetched or contains no results grid, that season SHALL be skipped with a warning, its existing statuses SHALL be left as they are, and the run SHALL still succeed.

#### Scenario: Article has no grid

- **GIVEN** a season article with no results grid
- **WHEN** verification runs
- **THEN** a warning names the season
- **AND** the other seasons are verified normally

#### Scenario: Reference returns an error

- **GIVEN** the reference API answers with an error or times out
- **WHEN** verification runs
- **THEN** existing statuses for that season are kept
- **AND** the run exits 0

### Requirement: Verification in the API

Match responses SHALL include `verification`: `null` when the match has no status, otherwise an object with `status`, `reference` (`wikipedia`) and `checked_at` (UTC). `/v1/matches` SHALL accept a `verification` filter taking one status.

#### Scenario: Verified match

- **WHEN** a client GETs a match whose status is `VERIFIED`
- **THEN** `verification` is `{"status": "VERIFIED", "reference": "wikipedia", "checked_at": "<UTC timestamp>"}`

#### Scenario: Competition without verification

- **WHEN** a client GETs a UEFA Champions League match
- **THEN** `verification` is `null`

#### Scenario: Listing mismatches

- **WHEN** a client GETs `/v1/matches?verification=MISMATCH`
- **THEN** only matches whose status is `MISMATCH` are returned

#### Scenario: Unknown status filter

- **WHEN** a client GETs `/v1/matches?verification=MAYBE`
- **THEN** the API responds 422 with the standard error envelope

### Requirement: Reference results for cups and tournaments

The system SHALL use as the verification reference the match boxes of the English Wikipedia article named by each cup or tournament season and of the sub-articles it links whose titles extend its own, each box used once. Qualifying sub-articles are read only for seasons holding qualifying matches; squad, other-edition and non-match sub-articles are not. Each box pairs with the stored match of the same teams, identified only through Wikidata QIDs, and, when the pairing recurs, the same date.

#### Scenario: Cup season verified from its article

- **GIVEN** DFB-Pokal 2024-25 names the article `2024–25 DFB-Pokal`
- **WHEN** verification runs for the DFB-Pokal
- **THEN** each of the 63 stored matches is paired with its box in that article and gets a status

#### Scenario: Pairing played twice

- **GIVEN** FA Cup 2023-24 stores Scarborough Athletic v Forest Green Rovers on 4 November (1–1) and on 12 December (2–4)
- **WHEN** verification runs
- **THEN** each stored match is compared with the box of the same date

#### Scenario: Reference box without a result

- **GIVEN** a box whose score reads `w/o`, `Walkover`, `Void`, `Bye` or `v`
- **WHEN** verification runs
- **THEN** the box gives no reference score: a stored match paired with it is `UNCONFIRMED` if it has a score, and gets no status otherwise

#### Scenario: Box with an awarded score

- **GIVEN** a box `3–0 (awd.)` and a stored awarded match 3–0 for the same pairing
- **WHEN** verification runs

#### Scenario: Season spread over several articles

- **GIVEN** CONMEBOL Copa Libertadores 2024 names the article `2024 Copa Libertadores`
- **WHEN** verification runs
- **THEN** the boxes of its `qualifying stages`, `group stage` and `final stages` sub-articles are read
- **AND** its `Femenina` and `de Futsal` sub-articles are not

#### Scenario: Separate qualification tournament

- **GIVEN** the UEFA Euro 2024 article links `UEFA Euro 2024 qualifying`, and the season holds no qualifying matches
- **WHEN** verification runs
- **THEN** the qualification article is not read

#### Scenario: Same match in the main article and a sub-article

- **GIVEN** the 2022 FIFA World Cup article and its `Group A` sub-article both show Qatar v Ecuador
- **WHEN** verification runs
- **THEN** the match is compared once

#### Scenario: Teams named the other way round

- **GIVEN** openfootball lists the 1990 quarter-final as Yugoslavia v Argentina, and the Wikipedia box as Argentina v Yugoslavia, both on 30 June 1990
- **WHEN** verification runs
- **THEN** they are compared, with the box's score and shoot-out read the other way round

### Requirement: Reference-only Wikidata items

A team in `seeds/teams.yaml` MAY list `reference_wikidata`: other Wikidata items that verification references use for the same side. Verification SHALL read them as the team's own item. They SHALL never be used for identity, and a seed load SHALL fail if one is another team's item.

#### Scenario: Dutch East Indies linked as Indonesia

- **GIVEN** the Dutch East Indies lists Indonesia's item as `reference_wikidata`, and Wikipedia's 1938 World Cup links the side as Indonesia
- **WHEN** verification runs
- **THEN** the Dutch East Indies' 1938 match is compared, not left unpaired

### Requirement: Unchanged seasons are not re-verified

After a complete verification of a season, the system SHALL store the title and revision ID of every reference page it read. Without `--full`, a season SHALL be verified again only when it was synced in the same run, has no complete verification stored for its current data, has a page whose current revision differs (or that now redirects elsewhere or no longer exists), or is due in the rotation.

#### Scenario: Nothing changed

- **GIVEN** a season verified on the previous run, not synced in this run, and whose pages have the same revisions
- **WHEN** verification runs, and the season isn't due in the rotation
- **THEN** the season's article isn't fetched
- **AND** its statuses and `checked_at` are unchanged

#### Scenario: Article edited

- **GIVEN** a season whose article has a new revision since its last verification
- **WHEN** verification runs
- **THEN** the season is verified again and its statuses follow the new article

#### Scenario: Sub-article edited

- **GIVEN** a tournament season whose group sub-article has a new revision
- **WHEN** verification runs
- **THEN** the season is verified again

#### Scenario: Season re-synced

- **GIVEN** a season whose data changed and was re-synced in this run
- **WHEN** verification runs
- **THEN** the season is verified again, whatever its pages' revisions

### Requirement: Verification rotation

A season whose last complete verification is more than seven days old SHALL be verified again, even when nothing visible changed. Each run SHALL take at most a seventh of its verifiable seasons (rounded up) this way, oldest first.

#### Scenario: Check older than a week

- **GIVEN** a season last verified eight days ago, in which nothing changed
- **WHEN** verification runs
- **THEN** the season is verified again

#### Scenario: Recent check

- **GIVEN** a season verified yesterday, in which nothing changed
- **WHEN** verification runs
- **THEN** the season isn't verified again

#### Scenario: Many checks due at once

- **GIVEN** 227 verifiable seasons, all last verified eight days ago, in which nothing changed
- **WHEN** verification runs
- **THEN** the 33 with the oldest checks are verified again, and the others on later runs

### Requirement: Incomplete verification keeps its state

A verification that doesn't complete SHALL NOT update the stored titles, revisions or time, so the season is due again on the next run.

#### Scenario: Reference unavailable

- **GIVEN** a season due for verification whose article can't be fetched
- **WHEN** verification runs
- **THEN** its statuses are unchanged and it is due again on the next run

### Requirement: Reference line-ups

For cups and tournaments, the system SHALL use as the events reference the line-up table that follows the match box paired with a stored match: the starters and substitutes who came on for each side, with their bookings, dismissals and substitutions. When the same match appears in several articles, the table SHALL be taken from the copy that records the most cards and substitutions. No other page SHALL be fetched for it.

#### Scenario: Table after a group match

- **GIVEN** the `2022 FIFA World Cup Group A` article shows Qatar v Ecuador followed by its line-ups
- **WHEN** verification runs for the 2022 World Cup
- **THEN** the stored events of Qatar v Ecuador are compared with that table

#### Scenario: Table only in the sub-article

- **GIVEN** the 2022 FIFA World Cup article shows Qatar v Ecuador without line-ups, and its `Group A` sub-article shows it with them
- **WHEN** verification runs
- **THEN** the sub-article's table is used

#### Scenario: Shorter copy in the knockout article

- **GIVEN** the 2010 knockout stage article repeats the final's line-ups without cards, and the `2010 FIFA World Cup final` article has them with cards
- **WHEN** verification runs
- **THEN** the final article's table is used

#### Scenario: Table without shirt numbers

- **GIVEN** a 1934 World Cup line-up table whose rows have a position and a name but no number
- **WHEN** verification runs
- **THEN** the table is read and compared like any other

### Requirement: Events status per match

Each stored match paired with a match box SHALL get an events status, separate from its result status: `VERIFIED` (the stored events and the table agree), `MISMATCH` (they differ), `UNCONFIRMED` (only the stored match has events) or `SOURCE_BEHIND` (only the table exists). A match with neither gets no events status, nor does a match with no paired box, nor a match of a season whose `lineups` coverage is `none`.

#### Scenario: Everything agrees

- **GIVEN** a stored match whose starters, substitutes, substitutions and cards all agree with its table
- **WHEN** verification runs
- **THEN** the match's events status is `VERIFIED`

#### Scenario: Missing dismissal

- **GIVEN** stored events for Serbia v Ghana (2010) with Luković booked at 73', and a table with Luković booked at 54' and sent off for a second yellow at 74'
- **WHEN** verification runs
- **THEN** the match's events status is `MISMATCH`
- **AND** the stored events are unchanged

#### Scenario: Box without a table

- **GIVEN** a stored 2010 Club World Cup semi-final with events, whose box has no line-up table
- **WHEN** verification runs
- **THEN** the match's events status is `UNCONFIRMED`

#### Scenario: Season that records no line-ups

- **GIVEN** UEFA Euro 2024, whose stored matches have no line-ups, and Wikipedia line-up tables for its matches
- **WHEN** verification runs
- **THEN** no match gets an events status

#### Scenario: League match

- **WHEN** verification runs for Premier League 2025-26, whose stored matches have events
- **THEN** no match gets an events status

### Requirement: Events comparison

The comparison SHALL cover, for both sides, the starters, the substitutes who came on, when each player went off or came on, and, for matches from 1970 on, the cards (player, kind, minute). Substitutions SHALL be compared only when the table records any for the match, and cards only when it records any: a table that lists the players alone says nothing about them. A Wikipedia second-yellow dismissal SHALL count as a `YELLOW` and a `SECOND_YELLOW`.

#### Scenario: Second yellow

- **GIVEN** a stored `YELLOW` at 54' and `SECOND_YELLOW` at 74' for a player, and `{{sent off|2|54|74}}` for him in the table
- **WHEN** verification runs
- **THEN** the cards agree

#### Scenario: Table without cards

- **GIVEN** a 2006 match whose stored events record bookings, and whose table records no card for either side
- **WHEN** verification runs
- **THEN** the cards aren't compared

#### Scenario: Cards before 1970

- **GIVEN** a 1966 match whose stored events record a caution that the table doesn't show, and whose line-ups agree
- **WHEN** verification runs
- **THEN** the match's events status is `VERIFIED`

### Requirement: Event minutes

Minutes SHALL agree when they differ by at most one. Added minutes SHALL be compared only when both sources have one, and extra time written as added time (`90+8'`) SHALL agree with the same minute written plainly (`98'`).

#### Scenario: Minute rounded differently

- **GIVEN** a stored booking at 18' and the same player's booking at 19' in the table
- **WHEN** verification runs
- **THEN** the bookings agree

#### Scenario: Extra time written as added time

- **GIVEN** a stored booking at `90+8'` and the same player's booking at `98'` in the table
- **WHEN** verification runs
- **THEN** the bookings agree

### Requirement: Player pairing

Players SHALL be paired within one side of one match: first by name, ignoring case, accents, punctuation, spaces and the captain mark, with German umlauts also read as written with an `e`; then by a single shared name word; then by shirt number, when both the stored player's squad entry and the table have one; then by the closest spelling, when each is the other's closest and close enough. A player left unpaired SHALL be a difference.

#### Scenario: Accents and case

- **GIVEN** a stored `Sergej MILINKOVIC-SAVIC` and a table row `Sergej Milinković-Savić`
- **WHEN** verification runs
- **THEN** they are the same player

#### Scenario: Common name

- **GIVEN** a stored `SAAD ALSHEEB` and a table row `Saad Al-Sheeb`
- **WHEN** verification runs
- **THEN** they are the same player

#### Scenario: Umlaut written with an e

- **GIVEN** a stored `Sepp HUEGI` and a table row `Josef Hügi`
- **WHEN** verification runs
- **THEN** they are the same player

#### Scenario: Shared first names

- **GIVEN** stored `AHMED HEGAZY` and `AHMED FATHI`, and table rows `Ahmed Fathy` and `Ahmed Hegazi`
- **WHEN** verification runs
- **THEN** each is paired with the closest spelling, not by the shared word `ahmed`

#### Scenario: Nickname

- **GIVEN** a stored `Jose ALTAFINI` with squad number 18, and a table row `Mazzola` with number 18
- **WHEN** verification runs
- **THEN** they are the same player

#### Scenario: Different player

- **GIVEN** a stored starter `Frank WALLACE` and a table starter `Robert Craddock`, with no shirt numbers
- **WHEN** verification runs
- **THEN** they aren't paired, and both are differences

### Requirement: Events disagreement report

Each verification run SHALL log one line per events `MISMATCH` and `SOURCE_BEHIND` match, naming the season, both teams and each difference with the stored and the reference value, and a summary line per season with the count of each events status, separate from the results summary. A season that isn't verified again SHALL log the same lines from its stored statuses, as for results.

#### Scenario: Mismatch is listed

- **GIVEN** a match whose events status is `MISMATCH`
- **WHEN** verification finishes
- **THEN** the log has a line starting `<competition> <season>: MISMATCH events <home> v <away>: stored vs wikipedia:` that names each difference

#### Scenario: Season summary

- **WHEN** verification of a season with events statuses finishes
- **THEN** the log has a line `<competition> <season>: events verified against wikipedia: VERIFIED=… MISMATCH=… UNCONFIRMED=… SOURCE_BEHIND=…`

### Requirement: Events verification in the API

Match responses SHALL include `events_verification`: `null` when the match has no events status, otherwise an object with `status`, `reference` (`wikipedia`) and `checked_at` (UTC). `/v1/matches` SHALL accept an `events_verification` filter taking one status. `verification` SHALL keep describing the result only.

#### Scenario: Verified events

- **WHEN** a client GETs a match whose events status is `VERIFIED`
- **THEN** `events_verification` is `{"status": "VERIFIED", "reference": "wikipedia", "checked_at": "<UTC timestamp>"}`

#### Scenario: Listing events mismatches

- **WHEN** a client GETs `/v1/matches?events_verification=MISMATCH`
- **THEN** only matches whose events status is `MISMATCH` are returned
