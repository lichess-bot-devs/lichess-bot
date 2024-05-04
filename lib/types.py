from typing import Any, Callable
from typing_extensions import TypedDict, NotRequired
from chess.engine import PovWdl, PovScore

JSON_REPLY_TYPE = dict[str, Any]
REQUESTS_PAYLOAD_TYPE = dict[str, Any]


class PerfType(TypedDict):
    games: NotRequired[int]
    rating: NotRequired[int]
    rd: NotRequired[int]
    sd: NotRequired[int]
    prov: NotRequired[bool]


class ProfileType(TypedDict):
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
    id: str
    username: str
    perfs: NotRequired[dict[str, PerfType]]
    createdAt: NotRequired[int]
    disabled: NotRequired[bool]
    tosViolation: NotRequired[bool]
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


class ReadableType(TypedDict):
    Evaluation: Callable[[PovScore], str]
    Winrate: Callable[[PovWdl], str]
    Hashfull: Callable[[int], str]
    Nodes: Callable[[int], str]
    Speed: Callable[[int], str]
    Tbhits: Callable[[int], str]
    Cpuload: Callable[[int], str]
    Movetime: Callable[[int], str]
