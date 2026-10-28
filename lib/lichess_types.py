"""Some type hints that can be accessed by all other python files."""
from typing import Any, TypedDict, Literal, TypeAlias, NotRequired
from collections.abc import Callable
from chess.engine import PovWdl, PovScore, PlayResult, Limit, Opponent
from chess import Move, Board
from queue import Queue
import logging
import datetime
from enum import Enum
from types import TracebackType

COMMANDS_TYPE: TypeAlias = list[str]
MOVE: TypeAlias = PlayResult | list[Move]
CORRESPONDENCE_QUEUE_TYPE: TypeAlias = Queue[tuple[str, str]]
LOGGING_QUEUE_TYPE: TypeAlias = Queue[logging.LogRecord]
REQUESTS_PAYLOAD_TYPE: TypeAlias = dict[str, str | int | bool]
GO_COMMANDS_TYPE: TypeAlias = dict[str, str]
EGTPATH_TYPE: TypeAlias = dict[str, str]
OPTIONS_GO_EGTB_TYPE: TypeAlias = dict[str, str | int | bool | EGTPATH_TYPE | GO_COMMANDS_TYPE | None]
OPTIONS_TYPE: TypeAlias = dict[str, str | int | bool | None]
HOMEMADE_ARGS_TYPE: TypeAlias = Limit | bool | MOVE

# Types that still use `Any`.
CONFIG_DICT_TYPE: TypeAlias = dict[str, Any]


class PerfType(TypedDict):
    """Type hint for `perf`."""

    games: NotRequired[int]
    rating: NotRequired[int]
    rd: NotRequired[int]
    sd: NotRequired[int]
    prov: NotRequired[bool]
    prog: NotRequired[int]


class ProfileType(TypedDict):
    """Type hint for `profile`."""

    country: NotRequired[str]
    location: NotRequired[str]
    bio: NotRequired[str]
    firstName: NotRequired[str]
    lastName: NotRequired[str]
    fideRating: NotRequired[int]
    uscfRating: NotRequired[int]
    ecfRating: NotRequired[int]
    cfcRating: NotRequired[int]
    dsbRating: NotRequired[int]
    links: NotRequired[str]


class UserProfileType(TypedDict):
    """Type hint for `user_profile`."""

    id: NotRequired[str]
    username: NotRequired[str]
    perfs: NotRequired[dict[str, PerfType]]
    createdAt: NotRequired[int]
    profile: NotRequired[ProfileType]
    seenAt: NotRequired[int]
    patron: NotRequired[int]
    verified: NotRequired[int]
    playTime: NotRequired[dict[str, int]]
    title: NotRequired[str]
    online: NotRequired[bool]
    url: NotRequired[str]
    followable: NotRequired[bool]
    following: NotRequired[bool]
    blocking: NotRequired[bool]
    followsYou: NotRequired[bool]
    count: NotRequired[dict[str, int]]


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


class InfoStrDict(TypedDict):
    """Type hints for the readable version of the information returned by chess engines."""

    score: NotRequired[PovScore]
    pv: NotRequired[list[Move]]
    depth: NotRequired[int]
    seldepth: NotRequired[int]
    time: NotRequired[float]
    nodes: NotRequired[int]
    nps: NotRequired[int]
    tbhits: NotRequired[int]
    multipv: NotRequired[int]
    currmove: NotRequired[str | Move]
    currmovenumber: NotRequired[int]
    hashfull: NotRequired[int]
    cpuload: NotRequired[int]
    refutation: NotRequired[str | dict[Move, list[Move]]]
    currline: NotRequired[dict[int, list[Move]]]
    ebf: NotRequired[float]
    wdl: NotRequired[PovWdl]
    string: NotRequired[str]
    ponderpv: NotRequired[str]
    Source: NotRequired[str]
    Pv: NotRequired[str]


InfoDictKeys: TypeAlias = Literal["score", "pv", "depth", "seldepth", "time", "nodes", "nps", "tbhits", "multipv", "currmove",
                       "currmovenumber", "hashfull", "cpuload", "refutation", "currline", "ebf", "wdl", "string",
                       "ponderpv", "Source", "Pv"]


InfoDictValue: TypeAlias = (PovScore | list[Move] | int | float | str | Move | dict[Move, list[Move]] |
                            dict[int, list[Move]] | PovWdl)


class PlayerType(TypedDict):
    """Type hint for information on a player."""

    title: NotRequired[str | None]
    rating: NotRequired[int]
    provisional: NotRequired[bool]
    aiLevel: NotRequired[int]
    id: NotRequired[str]
    username: NotRequired[str]
    name: NotRequired[str]
    online: NotRequired[bool]


class GameType(TypedDict):
    """Type hint for game."""

    gameId: NotRequired[str]
    fullId: NotRequired[str]
    color: NotRequired[str]
    fen: NotRequired[str]
    hasMoved: NotRequired[bool]
    isMyTurn: NotRequired[bool]
    lastMove: NotRequired[str]
    opponent: NotRequired[PlayerType]
    perf: NotRequired[str]
    rated: NotRequired[bool]
    secondsLeft: NotRequired[int]
    source: NotRequired[str]
    status: NotRequired[dict[str, str | int]]
    speed: NotRequired[str]
    variant: NotRequired[dict[str, str]]
    compat: NotRequired[dict[str, bool]]
    id: NotRequired[str]
    winner: NotRequired[str]
    ratingDiff: NotRequired[int]
    pgn: NotRequired[str]
    complete: NotRequired[bool]


class TimeControlType(TypedDict):
    """Type hint for time control."""

    increment: NotRequired[int]
    limit: NotRequired[int]
    show: NotRequired[str]
    type: NotRequired[str]
    daysPerTurn: NotRequired[int]
    initial: NotRequired[int]


class ChallengeType(TypedDict):
    """Type hint for challenge."""

    id: NotRequired[str]
    url: NotRequired[str]
    color: NotRequired[str]
    direction: NotRequired[str]
    rated: NotRequired[bool]
    speed: NotRequired[str]
    status: NotRequired[str]
    timeControl: NotRequired[TimeControlType]
    variant: NotRequired[dict[str, str]]
    challenger: NotRequired[PlayerType]
    destUser: NotRequired[PlayerType]
    perf: NotRequired[dict[str, str]]
    compat: NotRequired[dict[str, bool]]
    finalColor: NotRequired[str]
    declineReason: NotRequired[str]
    declineReasonKey: NotRequired[str]
    initialFen: NotRequired[str]
    error: NotRequired[str]
    ratelimit: NotRequired[dict[str, str | int]]
    bot_is_rate_limited: NotRequired[bool]
    opponent_is_rate_limited: NotRequired[bool]
    rate_limit_timeout: NotRequired[datetime.timedelta]


class EventType(TypedDict):
    """Type hint for event."""

    type: NotRequired[str]
    game: NotRequired[GameType]
    challenge: NotRequired[ChallengeType]
    error: NotRequired[str | None]


class GameStateType(TypedDict):
    """Type hint for game state."""

    type: NotRequired[str]
    moves: NotRequired[str]
    wtime: NotRequired[int]
    btime: NotRequired[int]
    winc: NotRequired[int]
    binc: NotRequired[int]
    wdraw: NotRequired[bool]
    bdraw: NotRequired[bool]
    status: NotRequired[str]
    winner: NotRequired[str]


class GameEventType(TypedDict):
    """Type hint for game event."""

    type: NotRequired[str]
    id: NotRequired[str]
    rated: NotRequired[bool]
    variant: NotRequired[dict[str, str]]
    cloak: NotRequired[dict[str, int]]
    speed: NotRequired[str]
    perf: NotRequired[dict[str, str]]
    createdAt: NotRequired[int]
    white: NotRequired[PlayerType]
    black: NotRequired[PlayerType]
    initialFen: NotRequired[str]
    state: NotRequired[GameStateType]
    username: NotRequired[str]
    text: NotRequired[str]
    room: NotRequired[str]
    gone: NotRequired[bool]
    claimWinInSeconds: NotRequired[int]
    moves: NotRequired[str]
    wtime: NotRequired[int]
    btime: NotRequired[int]
    winc: NotRequired[int]
    binc: NotRequired[int]
    wdraw: NotRequired[bool]
    bdraw: NotRequired[bool]
    status: NotRequired[str]
    winner: NotRequired[str]
    clock: NotRequired[TimeControlType]
    wtakeback: NotRequired[bool]
    btakeback: NotRequired[bool]


CONTROL_QUEUE_TYPE: TypeAlias = Queue[EventType]
PGN_QUEUE_TYPE: TypeAlias = Queue[EventType | None]


class PublicDataType(TypedDict):
    """Type hint for public data."""

    id: NotRequired[str]
    username: NotRequired[str]
    perfs: NotRequired[dict[str, PerfType]]
    flair: NotRequired[str]
    createdAt: NotRequired[int]
    disabled: NotRequired[bool]
    tosViolation: NotRequired[bool]
    profile: NotRequired[ProfileType]
    seenAt: NotRequired[int]
    patron: NotRequired[bool]
    verified: NotRequired[bool]
    playTime: NotRequired[dict[str, int]]
    title: NotRequired[str]
    url: NotRequired[str]
    playing: NotRequired[str]
    count: NotRequired[dict[str, int]]
    streaming: NotRequired[bool]
    streamer: NotRequired[dict[str, dict[str, str]]]
    followable: NotRequired[bool]
    following: NotRequired[bool]
    blocking: NotRequired[bool]
    followsYou: NotRequired[bool]


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


class ChessDBMoveType(TypedDict):
    """Type hint for a move returned by chessdb (opening & egtb)."""

    uci: NotRequired[str]
    san: NotRequired[str]
    score: NotRequired[int]
    rank: NotRequired[int]
    note: NotRequired[str]
    winrate: NotRequired[str]


class LichessPvType(TypedDict):
    """Type hint for a move returned by lichess cloud analysis."""

    moves: NotRequired[str]
    cp: NotRequired[int]


class LichessExplorerGameType(TypedDict):
    """Type hint for a game returned by lichess explorer."""

    id: NotRequired[str]
    winner: NotRequired[str | None]
    speed: NotRequired[str]
    mode: NotRequired[str]
    black: NotRequired[dict[str, str | int]]
    white: NotRequired[dict[str, str | int]]
    year: NotRequired[int]
    month: NotRequired[str]


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
    precise_dtz: int | None
    dtm: int | None
    category: str


class OnlineMoveType(TypedDict):
    """Type hint for a move returned by an online source."""

    # chessdb
    uci: str
    san: str
    score: int
    rank: int
    note: str
    winrate: str

    # lichess explorer
    # uci: str  (duplicate)
    # san: str  (duplicate)
    averageRating: int
    performance: int
    white: int
    black: int
    draws: int
    game: LichessExplorerGameType | None

    # lichess egtb
    # uci: str  (duplicate)
    # san: str  (duplicate)
    zeroing: bool
    checkmate: bool
    stalemate: bool
    variant_win: bool
    variant_loss: bool
    insufficient_material: bool
    dtz: int
    precise_dtz: int | None
    dtm: int | None
    dtc: int
    category: str


class OnlineType(TypedDict):
    """Type hint for moves returned by an online source."""

    # lichess egtb
    checkmate: NotRequired[bool]
    stalemate: NotRequired[bool]
    variant_win: NotRequired[bool]
    variant_loss: NotRequired[bool]
    insufficient_material: NotRequired[bool]
    dtz: NotRequired[int]
    precise_dtz: NotRequired[int | None]
    dtm: NotRequired[int | None]
    dtc: NotRequired[int]
    category: NotRequired[str]
    # moves: list[LichessEGTBMoveType]

    # lichess explorer
    white: NotRequired[int]
    black: NotRequired[int]
    draws: NotRequired[int]
    # moves: list[LichessExplorerMoveType]
    topGames: NotRequired[list[LichessExplorerGameType]]
    recentGames: NotRequired[list[LichessExplorerGameType]]
    opening: NotRequired[dict[str, str] | None]
    queuePosition: NotRequired[int]

    # lichess cloud
    fen: NotRequired[str]
    knodes: NotRequired[int]
    ply: NotRequired[str]
    depth: NotRequired[int]
    pvs: NotRequired[list[LichessPvType]]
    error: NotRequired[str]

    # chessdb (opening & egtb)
    status: NotRequired[str]
    # moves: list[ChessDBMoveType]
    # ply: str  (duplicate)
    score: NotRequired[int]
    # depth: int  (duplicate)
    pv: NotRequired[list[str]]
    pvSAN: NotRequired[list[str]]
    move: NotRequired[str]
    egtb: NotRequired[str]

    # all
    moves: NotRequired[list[OnlineMoveType]]


class TokenTestType(TypedDict):
    """Type hint for token test."""

    scopes: NotRequired[str]
    userId: NotRequired[str]
    expires: NotRequired[int]


TOKEN_TESTS_TYPE: TypeAlias = dict[str, TokenTestType]


class _BackoffDetails(TypedDict):
    """`_Details` from `backoff._typing`."""

    target: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    tries: int
    elapsed: float


class BackoffDetails(_BackoffDetails):
    """`Details` from `backoff._typing`."""

    wait: NotRequired[float]  # present in the on_backoff handler case for either decorator
    value: NotRequired[Any]  # present in the on_predicate decorator case


ENGINE_INPUT_ARGS_TYPE: TypeAlias = (OPTIONS_TYPE | type[BaseException] | BaseException | TracebackType | Board | Limit |
                                     str | bool | None)
ENGINE_INPUT_KWARGS_TYPE: TypeAlias = int | bool | list[Move] | Opponent | None
