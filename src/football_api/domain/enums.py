from enum import StrEnum


class TeamKind(StrEnum):
    CLUB = "CLUB"
    NATIONAL = "NATIONAL"


class CompetitionScope(StrEnum):
    DOMESTIC = "DOMESTIC"
    CONTINENTAL = "CONTINENTAL"
    INTERCONTINENTAL = "INTERCONTINENTAL"


class CompetitionFormat(StrEnum):
    LEAGUE = "LEAGUE"  # round-robin
    CUP = "CUP"  # knockout open to the national pyramid
    LEAGUE_CUP = "LEAGUE_CUP"  # knockout restricted to league clubs
    SUPER_CUP = "SUPER_CUP"  # champions' play-off
    TOURNAMENT = "TOURNAMENT"  # group or league phase, then knockouts


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
    PRELIMINARY = "PRELIMINARY"
    ROUND = "ROUND"  # a numbered knockout round; the number is the match's `matchday`
    LEAGUE = "LEAGUE"
    GROUP = "GROUP"
    PLAYOFF = "PLAYOFF"
    R32 = "R32"
    R16 = "R16"
    QF = "QF"
    SF = "SF"
    THIRD_PLACE = "THIRD_PLACE"
    FINAL = "FINAL"


class VerificationStatus(StrEnum):
    """How a stored result compares with a verification reference (match-verification spec)."""

    VERIFIED = "VERIFIED"
    MISMATCH = "MISMATCH"
    UNCONFIRMED = "UNCONFIRMED"  # only the stored match has a score
    SOURCE_BEHIND = "SOURCE_BEHIND"  # only the reference has one


class VerificationReference(StrEnum):
    WIKIPEDIA = "wikipedia"
