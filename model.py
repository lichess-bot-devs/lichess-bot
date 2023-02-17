import math
from urllib.parse import urljoin
import logging
import datetime
from enum import Enum
from timer import Timer
from config import Configuration
from typing import Dict, Any, Tuple, List, DefaultDict

logger = logging.getLogger(__name__)


class Challenge:
    def __init__(self, c_info: Dict[str, Any], user_profile: Dict[str, Any]) -> None:
        self.id = c_info["id"]
        self.rated = c_info["rated"]
        self.variant = c_info["variant"]["key"]
        self.perf_name = c_info["perf"]["name"]
        self.speed = c_info["speed"]
        self.increment: int = c_info.get("timeControl", {}).get("increment")
        self.base: int = c_info.get("timeControl", {}).get("limit")
        self.days: int = c_info.get("timeControl", {}).get("daysPerTurn")
        self.challenger = Player(c_info.get("challenger") or {})
        self.opponent = Player(c_info.get("destUser") or {})
        self.from_self = self.challenger.name == user_profile["username"]

    def is_supported_variant(self, challenge_cfg: Configuration) -> bool:
        return self.variant in challenge_cfg.variants

    def is_supported_time_control(self, challenge_cfg: Configuration) -> bool:
        speeds = challenge_cfg.time_controls
        increment_max: int = challenge_cfg.max_increment
        increment_min: int = challenge_cfg.min_increment
        base_max: int = challenge_cfg.max_base
        base_min: int = challenge_cfg.min_base
        days_max: int = challenge_cfg.max_days
        days_min: int = challenge_cfg.min_days

        if self.speed not in speeds:
            return False

        if self.base is not None and self.increment is not None:
            # Normal clock game
            return (increment_min <= self.increment <= increment_max
                    and base_min <= self.base <= base_max)
        elif self.days is not None:
            # Correspondence game
            return days_min <= self.days <= days_max
        else:
            # Unlimited game
            return days_max == math.inf

    def is_supported_mode(self, challenge_cfg: Configuration) -> bool:
        return ("rated" if self.rated else "casual") in challenge_cfg.modes

    def is_supported_recent(self, config: Configuration, recent_bot_challenges: DefaultDict[str, List[Timer]]) -> bool:
        # Filter out old challenges
        recent_bot_challenges[self.challenger.name] = [timer for timer
                                                       in recent_bot_challenges[self.challenger.name]
                                                       if not timer.is_expired()]
        max_recent_challenges = config.max_recent_bot_challenges
        return (not self.challenger.is_bot
                or max_recent_challenges is None
                or len(recent_bot_challenges[self.challenger.name]) < max_recent_challenges)

    def decline_due_to(self, requirement_met: bool, decline_reason: str) -> str:
        return "" if requirement_met else decline_reason

    def is_supported(self, config: Configuration,
                     recent_bot_challenges: DefaultDict[str, List[Timer]]) -> Tuple[bool, str]:
        try:
            if self.from_self:
                return True, ""

            decline_reason = (self.decline_due_to(config.accept_bot or not self.challenger.is_bot, "noBot")
                              or self.decline_due_to(not config.only_bot or self.challenger.is_bot, "onlyBot")
                              or self.decline_due_to(self.is_supported_time_control(config), "timeControl")
                              or self.decline_due_to(self.is_supported_variant(config), "variant")
                              or self.decline_due_to(self.is_supported_mode(config), "casual" if self.rated else "rated")
                              or self.decline_due_to(self.challenger.name not in config.block_list, "generic")
                              or self.decline_due_to(self.is_supported_recent(config, recent_bot_challenges), "later"))

            return not decline_reason, decline_reason

        except Exception:
            logger.exception(f"Error while checking challenge {self.id}:")
            return False, "generic"

    def score(self) -> int:
        rated_bonus = 200 if self.rated else 0
        challenger_master_title = self.challenger.title if not self.challenger.is_bot else None
        titled_bonus = 200 if challenger_master_title else 0
        challenger_rating_int = self.challenger.rating or 0
        return challenger_rating_int + rated_bonus + titled_bonus

    def mode(self) -> str:
        return "rated" if self.rated else "casual"

    def __str__(self) -> str:
        return f"{self.perf_name} {self.mode()} challenge from {self.challenger} ({self.id})"

    def __repr__(self) -> str:
        return self.__str__()


class Termination(str, Enum):
    MATE = "mate"
    TIMEOUT = "outoftime"
    RESIGN = "resign"
    ABORT = "aborted"
    DRAW = "draw"


class Game:
    def __init__(self, json: Dict[str, Any], username: str, base_url: str, abort_time: int) -> None:
        self.username = username
        self.id: str = json["id"]
        self.speed = json.get("speed")
        clock = json.get("clock") or {}
        ten_years_in_ms = 1000 * 3600 * 24 * 365 * 10
        self.clock_initial = clock.get("initial", ten_years_in_ms)
        self.clock_increment = clock.get("increment", 0)
        self.perf_name = (json.get("perf") or {}).get("name", "{perf?}")
        self.variant_name = json["variant"]["name"]
        self.mode = "rated" if json.get("rated") else "casual"
        self.white = Player(json["white"])
        self.black = Player(json["black"])
        self.initial_fen = json.get("initialFen")
        self.state: Dict[str, Any] = json["state"]
        self.is_white = (self.white.name or "").lower() == username.lower()
        self.my_color = "white" if self.is_white else "black"
        self.opponent_color = "black" if self.is_white else "white"
        self.me = self.white if self.is_white else self.black
        self.opponent = self.black if self.is_white else self.white
        self.base_url = base_url
        self.game_start = datetime.datetime.fromtimestamp(json["createdAt"]/1000, tz=datetime.timezone.utc)
        self.abort_time = Timer(abort_time)
        self.terminate_time = Timer((self.clock_initial + self.clock_increment) / 1000 + abort_time + 60)
        self.disconnect_time = Timer(0)

    def url(self) -> str:
        return f"{self.short_url()}/{self.my_color}"

    def short_url(self) -> str:
        return urljoin(self.base_url, self.id)

    def pgn_event(self) -> str:
        if self.variant_name in ["Standard", "From Position"]:
            return f"{self.mode.title()} {self.perf_name.title()} game"
        else:
            return f"{self.mode.title()} {self.variant_name} game"

    def time_control(self) -> str:
        return f"{int(self.clock_initial/1000)}+{int(self.clock_increment/1000)}"

    def is_abortable(self) -> bool:
        # Moves are separated by spaces. A game is abortable when less
        # than two moves (one from each player) have been played.
        return " " not in self.state["moves"]

    def ping(self, abort_in: int, terminate_in: int, disconnect_in: int) -> None:
        if self.is_abortable():
            self.abort_time = Timer(abort_in)
        self.terminate_time = Timer(terminate_in)
        self.disconnect_time = Timer(disconnect_in)

    def should_abort_now(self) -> bool:
        return self.is_abortable() and self.abort_time.is_expired()

    def should_terminate_now(self) -> bool:
        return self.terminate_time.is_expired()

    def should_disconnect_now(self) -> bool:
        return self.disconnect_time.is_expired()

    def my_remaining_seconds(self) -> float:
        wtime: int = self.state["wtime"]
        btime: int = self.state["btime"]
        return (wtime if self.is_white else btime) / 1000

    def result(self) -> str:
        class GameEnding(str, Enum):
            WHITE_WINS = "1-0"
            BLACK_WINS = "0-1"
            DRAW = "1/2-1/2"
            INCOMPLETE = "*"

        winner = self.state.get("winner")
        termination = self.state.get("status")

        if winner == "white":
            result = GameEnding.WHITE_WINS
        elif winner == "black":
            result = GameEnding.BLACK_WINS
        elif termination == Termination.DRAW:
            result = GameEnding.DRAW
        else:
            result = GameEnding.INCOMPLETE

        return result.value

    def __str__(self) -> str:
        return f"{self.url()} {self.perf_name} vs {self.opponent} ({self.id})"

    def __repr__(self) -> str:
        return self.__str__()


class Player:
    def __init__(self, json: Dict[str, Any]) -> None:
        self.name: str = json.get("name", "")
        self.title = json.get("title")
        self.is_bot = self.title == "BOT"
        self.rating = json.get("rating")
        self.provisional = json.get("provisional")
        self.aiLevel = json.get("aiLevel")

    def __str__(self) -> str:
        if self.aiLevel:
            return f"AI level {self.aiLevel}"
        else:
            rating = f'{self.rating}{"?" if self.provisional else ""}'
            return f'{self.title or ""} {self.name} ({rating})'.strip()

    def __repr__(self) -> str:
        return self.__str__()
