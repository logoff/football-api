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


class Played(StrEnum):
    """How much of a completed match was played: to the end, until it was abandoned, or not at all."""

    FULL = "FULL"
    PARTIAL = "PARTIAL"
    NONE = "NONE"


class Publisher(StrEnum):
    """Who publishes a season's source data."""

    OPENFOOTBALL = "openfootball"
    WIKIPEDIA = "Wikipedia"


class License(StrEnum):
    """SPDX identifier of the license a season's data is served under."""

    CC0 = "CC0-1.0"
    CC_BY_SA = "CC-BY-SA-4.0"


class DecidedBy(StrEnum):
    REGULAR = "REGULAR"
    EXTRA_TIME = "EXTRA_TIME"
    PENALTIES = "PENALTIES"


class Side(StrEnum):
    HOME = "HOME"
    AWAY = "AWAY"


class LineupRole(StrEnum):
    STARTER = "STARTER"
    SUBSTITUTE = "SUBSTITUTE"  # came on during the match; the unused bench isn't recorded


class CardKind(StrEnum):
    YELLOW = "YELLOW"
    SECOND_YELLOW = "SECOND_YELLOW"  # the sending-off; the first yellow is its own card
    RED = "RED"


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
    FIFTH_PLACE = "FIFTH_PLACE"
    FINAL = "FINAL"


class VerificationStatus(StrEnum):
    """How a stored result compares with a verification reference (match-verification spec)."""

    VERIFIED = "VERIFIED"
    MISMATCH = "MISMATCH"
    UNCONFIRMED = "UNCONFIRMED"  # only the stored match has a score
    SOURCE_BEHIND = "SOURCE_BEHIND"  # only the reference has one


class VerificationReference(StrEnum):
    WIKIPEDIA = "wikipedia"


class VerificationAspect(StrEnum):
    """What of a match a status is about (verify-match-events D4)."""

    RESULT = "RESULT"  # the score and shootout
    EVENTS = "EVENTS"  # line-ups, substitutions and cards
