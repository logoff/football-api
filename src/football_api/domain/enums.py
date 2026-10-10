from enum import StrEnum


class TeamKind(StrEnum):
    CLUB = "CLUB"
    NATIONAL = "NATIONAL"


class CompetitionScope(StrEnum):
    DOMESTIC = "DOMESTIC"
    CONTINENTAL = "CONTINENTAL"
    INTERCONTINENTAL = "INTERCONTINENTAL"


class SeasonStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class MatchStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    POSTPONED = "POSTPONED"


class DecidedBy(StrEnum):
    REGULAR = "REGULAR"
    EXTRA_TIME = "EXTRA_TIME"
    PENALTIES = "PENALTIES"


class Side(StrEnum):
    HOME = "HOME"
    AWAY = "AWAY"


class EntityType(StrEnum):
    COMPETITION = "competition"
    SEASON = "season"
    TEAM = "team"
    VENUE = "venue"
    PLAYER = "player"
    MATCH = "match"


class Coverage(StrEnum):
    FULL = "full"
    NONE = "none"


class Stage(StrEnum):
    QUALIFYING = "QUALIFYING"
    LEAGUE = "LEAGUE"
    GROUP = "GROUP"
    PLAYOFF = "PLAYOFF"
    R32 = "R32"
    R16 = "R16"
    QF = "QF"
    SF = "SF"
    THIRD_PLACE = "THIRD_PLACE"
    FINAL = "FINAL"
