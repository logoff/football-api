## MODIFIED Requirements

### Requirement: Wikipedia season source

A season seeded with `wikipedia_source` SHALL be read from the match boxes, or for a league season the results grids, of the English Wikipedia pages it lists, each pinned to a revision ID, and SHALL NOT be read from the live pages. The pages are the season article and the sub-articles it needs. Each box is used once. A season seeded with both a Wikipedia source and an openfootball file SHALL fail the seed load.

#### Scenario: Season read from pinned revisions

- **GIVEN** European Cup 1955-56 pinned to revision 1384458360 of `1955–56 European Cup`
- **WHEN** the sync runs
- **THEN** the season has the 29 matches of that revision's boxes, each `COMPLETED` with its date and score

#### Scenario: Article edited after pinning

- **GIVEN** a pinned season whose article has since been edited on Wikipedia
- **WHEN** the sync runs
- **THEN** the stored matches still come from the pinned revision

#### Scenario: Unrelated sub-articles

- **GIVEN** the article `1960–61 European Cup`, which links `1960–61 European Cup Winners' Cup`
- **WHEN** its pins are written
- **THEN** the Winners' Cup article is not pinned, and none of its matches are stored in the European Cup season

#### Scenario: League season read from its results grid

- **GIVEN** La Liga 1929 pinned to a revision of `1929 La Liga`, whose results grid has 10 clubs
- **WHEN** the sync runs
- **THEN** the season has 90 `COMPLETED` matches with stage `LEAGUE`, one per filled cell, each with its score and no date
- **AND** the two relegation play-off boxes on the same page are not stored

## ADDED Requirements

### Requirement: Results grid cells

Each cell of a results grid SHALL give one match: the club of its row at home, the club of its column away, and the cell's score. Rows and columns SHALL pair by position, so the diagonal is skipped even where a row and its column name the club differently. An empty cell SHALL be stored `CANCELLED` without a score.

#### Scenario: Row and column named differently

- **GIVEN** the 1946-47 grid, whose row says `Atlético Bilbao` and whose column says `Athletic Bilbao`, both resolving to one QID
- **WHEN** it is read
- **THEN** the season has 182 matches and no club plays itself

#### Scenario: Row and column that don't match

- **GIVEN** a grid whose row and column at the same position resolve to different QIDs
- **WHEN** the season is synced
- **THEN** the season fails with an error naming the page, revision and both clubs

#### Scenario: Annulled match

- **GIVEN** the 1979-80 grid, whose Málaga v Salamanca cell is empty because the result was annulled
- **WHEN** it is read
- **THEN** that match is `CANCELLED` without a score, and the other 305 are `COMPLETED`

### Requirement: Grid sections

A season read from grids SHALL read the one grid on its pages when there is only one. When there are several, the season seed SHALL name the top-level section of each grid to read, and every grid whose top-level section is named is read. A page with several grids and no sections named, or a named section with no grid, SHALL fail the season. The stage and group SHALL come from the section heading, as for match boxes.

#### Scenario: Second phase in groups

- **GIVEN** La Liga 1986-87 seeded with the sections `Regular season`, `Championship group`, `Intermediate group` and `Relegation group`
- **WHEN** it is synced
- **THEN** the season has 306 `LEAGUE` matches and 90 `GROUP` matches, 30 in each of three groups

#### Scenario: Grid of another competition on the page

- **GIVEN** La Liga 1950-51, whose page also has a relegation group grid with Segunda clubs, seeded with the section `Results` only
- **WHEN** it is synced
- **THEN** the season has the 240 matches of the league grid and none of the relegation group

#### Scenario: Several grids and no sections

- **GIVEN** a season whose pinned page has two grids and whose seed names no section
- **WHEN** the season is synced
- **THEN** the season fails with an error naming the page, revision and the headings of the grids

### Requirement: Awarded matches in grids

A grid can't mark a match as awarded. In a season read from grids, a match listed in `seeds/awarded.yaml` SHALL be stored flagged `awarded`, with the score the grid gives and the curated `played` value. An entry for a pairing the season doesn't have SHALL fail that season's sync.

#### Scenario: Awarded match from the seed

- **GIVEN** La Liga 1979-80, and an `awarded.yaml` entry for Málaga v Almería curated as `NONE`
- **WHEN** it is synced
- **THEN** that match is `COMPLETED`, `awarded` and `played` `NONE`, with the grid's score
