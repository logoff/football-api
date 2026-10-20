# Proposal

## Why

Line-ups, substitutions and cards link to a player only where that season's squad list is ingested. Squads are ingested for just four tournament editions. So of 28,306 World Cup line-up entries only 1,995 reference a player, and of 6,393 Club World Cup entries only 1,990. Everything else is a bare name.

openfootball publishes a squad file for every World Cup and Club World Cup, and for Euro 2021 and Copa América 2021. Adding them links nearly every event, and the goals of those seasons too.

## What Changes

- **Seeds:** squads for the 44 tournament seasons that have a squad file and don't yet use it: 22 World Cups (1930–2018 and 2026), 20 Club World Cups (2000–2023), Euro 2021 and Copa América 2021.
- **Parser:** the `more` squad format accepts lines without a shirt number. The World Cup squads before 1954 have none, and none of their 1,174 players were read.
- **Name matching:** a name that matches no one exactly or by surname is compared again with spaces ignored, still only when exactly one squad member matches. openfootball's own files sometimes split a name differently, as in `Park Jisung` and `PARK Ji Sung`.
- **Teams:** `Türkiye` is added as a spelling of Turkey (2026 World Cup squads).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `catalog`: player coverage now covers every World Cup and Club World Cup, and Euro and Copa América 2021.
- `match-events`: event player resolution also ignores spaces when nothing else matches.

## Impact

- **Seeds:** `competitions.yaml` and `teams.yaml`.
- **Code:** the squad parser and the name resolver used by goals and events.
- **Data:** about 15,000 more players. Event and goal rows of those seasons gain player references on the next sync.
- **Database and API:** no change.
