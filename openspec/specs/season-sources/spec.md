# season-sources Specification

## Purpose

Say where each season's data comes from and under which license it is served, so that clients can meet the terms of every source, including sources that require attribution and share-alike.

## Requirements

### Requirement: Season source

Every season SHALL name its source. The source gives the publisher (`openfootball` or `Wikipedia`), the license as an SPDX identifier (`CC0-1.0` or `CC-BY-SA-4.0`) and the pages it was read from. Each page has a URL, and for Wikipedia the URL names the exact revision read. The source SHALL be served on the season in REST and GraphQL.

#### Scenario: Season from openfootball

- **GIVEN** Champions League 2011-12, synced from openfootball
- **WHEN** a client GETs the season
- **THEN** its source has publisher `openfootball` and license `CC0-1.0`
- **AND** its pages link the openfootball file it was read from

#### Scenario: Season from Wikipedia

- **GIVEN** European Cup 1955-56, synced from the article `1955–56 European Cup` pinned to a revision
- **WHEN** a client GETs the season
- **THEN** its source has publisher `Wikipedia` and license `CC-BY-SA-4.0`
- **AND** its pages link that article at that revision (`…/w/index.php?oldid=<revision>`)

#### Scenario: Pin moved

- **GIVEN** a Wikipedia season whose pin moves to a newer revision
- **WHEN** the sync runs
- **THEN** the season's source links the new revision

### Requirement: License on matches

Every match SHALL carry the license of its season's source, in REST and GraphQL. That way, a client listing matches across seasons knows the terms that apply to each one.

#### Scenario: Mixed listing

- **GIVEN** Real Madrid's Champions League matches of 2010-11 (Wikipedia) and 2011-12 (openfootball)
- **WHEN** a client lists them
- **THEN** each match from 2010-11 has license `CC-BY-SA-4.0`, and each from 2011-12 has `CC0-1.0`

### Requirement: Attribution and share-alike

The README SHALL credit every source and name its license, and SHALL list the seasons taken from each one. It SHALL also state that data from CC BY-SA seasons is served under CC BY-SA 4.0, and that each such season links the page revisions it was taken from and their history.

#### Scenario: Reading the terms

- **WHEN** someone reads the README's data sources section
- **THEN** it names openfootball (CC0 1.0) and English Wikipedia (CC BY-SA 4.0), with the seasons taken from each
- **AND** it says that matches, standings and every other value derived from a Wikipedia season are served under CC BY-SA 4.0
