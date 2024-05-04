"""Some type hints that can be accessed by all other python files."""
from typing import Any, Callable, Optional, Union, TypedDict, Literal
from chess.engine import PovWdl, PovScore, PlayResult
from chess import Move
from queue import Queue
import logging
from enum import Enum

OPTIONS_TYPE = dict[str, Union[str, int, bool, None]]
COMMANDS_TYPE = list[str]
MOVE = Union[PlayResult, list[Move]]
CORRESPONDENCE_QUEUE_TYPE = Queue[str]
LOGGING_QUEUE_TYPE = Queue[logging.LogRecord]
REQUESTS_PAYLOAD_TYPE = dict[str, Union[str, int, bool]]

# Types that still use `Any`.
JSON_REPLY_TYPE = dict[str, Any]
OPTIONS_GO_EGTB_TYPE = dict[str, Any]
CONFIG_DICT_TYPE = dict[str, Any]


class PerfType(TypedDict, total=False):
    """Type hint for `perf`."""

    games: int
    rating: int
    rd: int
    sd: int
    prov: bool


class ProfileType(TypedDict, total=False):
    """Type hint for `profile`."""

    country: str
    location: str
    bio: str
    firstName: str
    lastName: str
    fideRating: int
    uscfRating: int
    ecfRating: int
    cfcRating: int
    dsbRating: int
    links: str


class UserProfileType(TypedDict, total=False):
    """Type hint for `user_profile`."""

    id: str
    username: str
    perfs: dict[str, PerfType]
    createdAt: int
    disabled: bool
    tosViolation: bool
    profile: ProfileType
    seenAt: int
    patron: int
    verified: int
    playTime: dict[str, int]
    title: str
    online: bool
    url: str
    followable: bool
    following: bool
    blocking: bool
    followsYou: bool


class ReadableType(TypedDict):
    """Type hint for `readable`."""

    Evaluation: Callable[[PovScore], str]
    Winrate: Callable[[PovWdl], str]
    Hashfull: Callable[[int], str]
    Nodes: Callable[[int], str]
    Speed: Callable[[int], str]
    Tbhits: Callable[[int], str]
    Cpuload: Callable[[int], str]
    Movetime: Callable[[int], str]


class ChessDBEGTBMoveType(TypedDict):
    """Type hint for the moves returned by the chessdb egtb."""

    uci: str
    san: str
    score: int
    rank: int
    note: str


class LichessEGTBMoveType(TypedDict):
    """Type hint for the moves returned by the lichess egtb."""

    uci: str
    san: str
    zeroing: bool
    checkmate: bool
    stalemate: bool
    variant_win: bool
    variant_loss: bool
    insufficient_material: bool
    dtz: int
    precise_dtz: Optional[int]
    dtm: Optional[int]
    category: str


class InfoStrDict(TypedDict, total=False):
    """Type hints for the readable version of the information returned by chess engines."""

    score: PovScore
    pv: list[Move]
    depth: int
    seldepth: int
    time: float
    nodes: int
    nps: int
    tbhits: int
    multipv: int
    currmove: Union[str, Move]
    currmovenumber: int
    hashfull: int
    cpuload: int
    refutation: Union[str, dict[Move, list[Move]]]
    currline: dict[int, list[Move]]
    ebf: float
    wdl: PovWdl
    string: str
    ponderpv: str
    Source: str
    Pv: str


InfoDictKeys = Literal["score", "pv", "depth", "seldepth", "time", "nodes", "nps", "tbhits", "multipv", "currmove",
                       "currmovenumber", "hashfull", "cpuload", "refutation", "currline", "ebf", "wdl", "string",
                       "ponderpv", "Source", "Pv"]


InfoDictValue = Union[PovScore, list[Move], int, float, str, Move, dict[Move, list[Move]], dict[int, list[Move]], PovWdl]


class PlayerType(TypedDict, total=False):
    """Type hint for information on a player."""

    title: str
    rating: int
    provisional: bool
    aiLevel: int
    id: str
    username: str
    name: str
    online: bool


class GameType(TypedDict, total=False):
    """Type hint for game."""

    gameId: str
    fullId: str
    color: str
    fen: str
    hasMoved: bool
    isMyTurn: bool
    lastMove: str
    opponent: PlayerType
    perf: str
    rated: bool
    secondsLeft: int
    source: str
    status: dict[str, Union[str, int]]
    speed: str
    variant: dict[str, str]
    compat: dict[str, bool]
    id: str
    winner: str
    ratingDiff: int
    pgn: str
    complete: bool


class TimeControlType(TypedDict, total=False):
    """Type hint for time control."""

    increment: int
    limit: int
    show: str
    type: str
    daysPerTurn: int
    initial: int


class ChallengeType(TypedDict, total=False):
    """Type hint for challenge."""

    id: str
    url: str
    color: str
    direction: str
    rated: bool
    speed: str
    status: str
    timeControl: TimeControlType
    variant: dict[str, str]
    challenger: PlayerType
    destUser: PlayerType
    perf: dict[str, str]
    compat: dict[str, bool]
    finalColor: str
    declineReason: str
    declineReasonKey: str
    initialFen: str


class EventType(TypedDict, total=False):
    """Type hint for event."""

    type: str
    game: GameType
    challenge: ChallengeType
    error: Optional[str]


class GameStateType(TypedDict, total=False):
    """Type hint for game state."""

    type: str
    moves: str
    wtime: int
    btime: int
    winc: int
    binc: int
    wdraw: bool
    bdraw: bool
    status: str
    winner: str


class GameEventType(TypedDict, total=False):
    """Type hint for game event."""

    type: str
    id: str
    rated: bool
    variant: dict[str, str]
    cloak: dict[str, int]
    speed: str
    perf: dict[str, str]
    createdAt: int
    white: PlayerType
    black: PlayerType
    initialFen: str
    state: GameStateType
    username: str
    text: str
    room: str
    gone: bool
    claimWinInSeconds: int
    moves: str
    wtime: int
    btime: int
    winc: int
    binc: int
    wdraw: bool
    bdraw: bool
    status: str
    winner: str
    clock: TimeControlType
    wtakeback: bool
    btakeback: bool


CONTROL_QUEUE_TYPE = Queue[EventType]


class PublicDataType(TypedDict, total=False):
    """Type hint for public data."""

    id: str
    username: str
    perfs: dict[str, PerfType]
    flair: str
    createdAt: int
    disabled: bool
    tosViolation: bool
    profile: ProfileType
    seenAt: int
    patron: bool
    verified: bool
    playTime: dict[str, int]
    title: str
    url: str
    playing: str
    count: dict[str, int]
    streaming: bool
    streamer: dict[str, dict[str, str]]
    followable: bool
    following: bool
    blocking: bool
    followsYou: bool


class FilterType(str, Enum):
    """What to do if the opponent declines our challenge."""

    NONE = "none"
    """Will still challenge the opponent."""
    COARSE = "coarse"
    """Won't challenge the opponent again."""
    FINE = "fine"
    """
    Won't challenge the opponent to a game of the same mode, speed, and variant
    based on the reason for the opponent declining the challenge.
    """
