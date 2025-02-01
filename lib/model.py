"""Store information about a challenge, game or player in a class."""
import math
from urllib.parse import urljoin
import logging
import datetime
from enum import Enum
from lib.timer import Timer, msec, seconds, sec_str, to_msec, to_seconds, years
from lib.config import Configuration
from collections import defaultdict, Counter
from lib.lichess_types import UserProfileType, ChallengeType, GameEventType, PlayerType

logger = logging.getLogger(__name__)


class Challenge:
    """Store information about a challenge."""

    def __init__(self, challenge_info: ChallengeType, user_profile: UserProfileType) -> None:
        """:param user_profile: Information about our bot."""
        self.id = challenge_info["id"]
        self.rated = challenge_info["rated"]
        self.variant = challenge_info["variant"]["key"]
        self.perf_name = challenge_info["perf"]["name"]
        self.speed = challenge_info["speed"]
        self.increment = challenge_info.get("timeControl", {}).get("increment")
        self.base = challenge_info.get("timeControl", {}).get("limit")
        self.days = challenge_info.get("timeControl", {}).get("daysPerTurn")
        self.challenger = Player(challenge_info.get("challenger") or {})
        self.challenge_target = Player(challenge_info.get("destUser") or {})
        self.from_self = self.challenger.name == user_profile["username"]
        self.initial_fen = challenge_info.get("initialFen", "startpos")
        color = challenge_info["color"]
        self.color = color if color != "random" else challenge_info["finalColor"]
        self.time_control = challenge_info["timeControl"]

    def is_supported_variant(self, challenge_cfg: Configuration) -> bool:
        """Check whether the variant is supported."""
        return self.variant in challenge_cfg.variants

    def is_supported_time_control(self, challenge_cfg: Configuration) -> bool:
        """Check whether the time control is supported."""
        speeds = challenge_cfg.time_controls
        increment_max: int = challenge_cfg.max_increment
        increment_min: int = challenge_cfg.min_increment
        base_max: int = challenge_cfg.max_base
        base_min: int = challenge_cfg.min_base
        days_max: float = challenge_cfg.max_days
        days_min: float = challenge_cfg.min_days

        if self.speed not in speeds:
            return False

        require_non_zero_increment = (self.challenger.is_bot
                                      and self.speed == "bullet"
                                      and challenge_cfg.bullet_requires_increment)
        increment_min = max(increment_min, 1 if require_non_zero_increment else 0)

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
        """Check whether the mode is supported."""
        return ("rated" if self.rated else "casual") in challenge_cfg.modes

    def is_supported_recent(self, config: Configuration, recent_bot_challenges: defaultdict[str, list[Timer]]) -> bool:
        """Check whether we have played a lot of games with this opponent recently. Only used when the opponent is a BOT."""
        # Filter out old challenges
        recent_bot_challenges[self.challenger.name] = [timer for timer
                                                       in recent_bot_challenges[self.challenger.name]
                                                       if not timer.is_expired()]
        max_recent_challenges = config.max_recent_bot_challenges
        return (not self.challenger.is_bot
                or max_recent_challenges is None
                or len(recent_bot_challenges[self.challenger.name]) < max_recent_challenges)

    def decline_due_to(self, requirement_met: bool, decline_reason: str) -> str:
        """
        Get the reason lichess-bot declined an incoming challenge.

        :param requirement_met: Whether a requirement is met.
        :param decline_reason: The reason we declined the challenge if the requirement wasn't met.
        :return: `decline_reason` if `requirement_met` is false else returns an empty string.
        """
        return "" if requirement_met else decline_reason

    def is_supported(self, config: Configuration, recent_bot_challenges: defaultdict[str, list[Timer]],
                     players_with_active_games: Counter[str]) -> tuple[bool, str]:
        """Whether the challenge is supported."""
        try:
            if self.from_self:
                return True, ""

            from extra_game_handlers import is_supported_extra

            allowed_opponents: list[str] = list(filter(None, config.allow_list)) or [self.challenger.name]
            decline_reason = (self.decline_due_to(config.accept_bot or not self.challenger.is_bot, "noBot")
                              or self.decline_due_to(not config.only_bot or self.challenger.is_bot, "onlyBot")
                              or self.decline_due_to(self.is_supported_time_control(config), "timeControl")
                              or self.decline_due_to(self.is_supported_variant(config), "variant")
                              or self.decline_due_to(self.is_supported_mode(config), "casual" if self.rated else "rated")
                              or self.decline_due_to(self.challenger.name not in config.block_list, "generic")
                              or self.decline_due_to(self.challenger.name in allowed_opponents, "generic")
                              or self.decline_due_to(self.is_supported_recent(config, recent_bot_challenges), "later")
                              or self.decline_due_to(players_with_active_games[self.challenger.name]
                                                     < config.max_simultaneous_games_per_user, "later")
                              or self.decline_due_to(is_supported_extra(self), "generic"))

            return not decline_reason, decline_reason

        except Exception:
            logger.exception(f"Error while checking challenge {self.id}:")
            return False, "generic"

    def score(self) -> int:
        """Give a rating estimate to the opponent."""
        rated_bonus = 200 if self.rated else 0
        challenger_master_title = self.challenger.title if not self.challenger.is_bot else None
        titled_bonus = 200 if challenger_master_title else 0
        challenger_rating_int = self.challenger.rating or 0
        return challenger_rating_int + rated_bonus + titled_bonus

    def mode(self) -> str:
        """Get the mode of the challenge (rated or casual)."""
        return "rated" if self.rated else "casual"

    def __str__(self) -> str:
        """Get a string representation of `Challenge`."""
        return f"{self.perf_name} {self.mode()} challenge from {self.challenger} ({self.id})"

    def __repr__(self) -> str:
        """Get a string representation of `Challenge`."""
        return self.__str__()


class Termination(str, Enum):
    """The possible game terminations."""

    MATE = "mate"
    TIMEOUT = "outoftime"
    RESIGN = "resign"
    ABORT = "aborted"
    DRAW = "draw"


class Game:
    """Store information about a game."""

    def __init__(self, game_info: GameEventType, username: str, base_url: str, abort_time: datetime.timedelta) -> None:
        """:param abort_time: How long to wait before aborting the game."""
        self.username = username
        self.id = game_info["id"]
        self.speed = game_info.get("speed")
        clock = game_info.get("clock") or {}
        ten_years_in_ms = to_msec(years(10))
        self.clock_initial = msec(clock.get("initial", ten_years_in_ms))
        self.clock_increment = msec(clock.get("increment", 0))
        self.perf_name = (game_info.get("perf") or {}).get("name", "{perf?}")
        self.variant_name = game_info["variant"]["name"]
        self.mode = "rated" if game_info.get("rated") else "casual"
        self.white = Player(game_info["white"])
        self.black = Player(game_info["black"])
        self.initial_fen = game_info.get("initialFen")
        self.state = game_info["state"]
        self.is_white = (self.white.name or "").lower() == username.lower()
        self.my_color = "white" if self.is_white else "black"
        self.opponent_color = "black" if self.is_white else "white"
        self.me = self.white if self.is_white else self.black
        self.opponent = self.black if self.is_white else self.white
        self.base_url = base_url
        self.game_start = datetime.datetime.fromtimestamp(to_seconds(msec(game_info["createdAt"])),
                                                          tz=datetime.timezone.utc)
        self.abort_time = Timer(abort_time)
        self.terminate_time = Timer(self.clock_initial + self.clock_increment + abort_time + seconds(60))
        self.disconnect_time = Timer(seconds(0))

    def url(self) -> str:
        """Get the url of the game."""
        return f"{self.short_url()}/{self.my_color}"

    def short_url(self) -> str:
        """Get the short url of the game."""
        return urljoin(self.base_url, self.id)

    def pgn_event(self) -> str:
        """Get the event to write in the PGN file."""
        if self.variant_name in ["Standard", "From Position"]:
            return f"{self.mode.title()} {self.perf_name.title()} game"
        else:
            return f"{self.mode.title()} {self.variant_name} game"

    def time_control(self) -> str:
        """Get the time control of the game."""
        return f"{sec_str(self.clock_initial)}+{sec_str(self.clock_increment)}"

    def is_abortable(self) -> bool:
        """Whether the game can be aborted."""
        # Moves are separated by spaces. A game is abortable when less
        # than two moves (one from each player) have been played.
        return " " not in self.state["moves"]

    def ping(self, abort_in: datetime.timedelta, terminate_in: datetime.timedelta, disconnect_in: datetime.timedelta) -> None:
        """
        Tell the bot when to abort, terminate, and disconnect from a game.

        :param abort_in: How many seconds to wait before aborting.
        :param terminate_in: How many seconds to wait before terminating.
        :param disconnect_in: How many seconds to wait before disconnecting.
        """
        if self.is_abortable():
            self.abort_time = Timer(abort_in)
        self.terminate_time = Timer(terminate_in)
        self.disconnect_time = Timer(disconnect_in)

    def should_abort_now(self) -> bool:
        """Whether we should abort the game."""
        return self.is_abortable() and self.abort_time.is_expired()

    def should_terminate_now(self) -> bool:
        """Whether we should terminate the game."""
        return self.terminate_time.is_expired()

    def should_disconnect_now(self) -> bool:
        """Whether we should disconnect form the game."""
        return self.disconnect_time.is_expired()

    def my_remaining_time(self) -> datetime.timedelta:
        """How many seconds we have left."""
        wtime = msec(self.state["wtime"])
        btime = msec(self.state["btime"])
        return wtime if self.is_white else btime

    def result(self) -> str:
        """Get the result of the game."""
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
        elif termination in [Termination.DRAW, Termination.TIMEOUT]:
            result = GameEnding.DRAW
        else:
            result = GameEnding.INCOMPLETE

        return result.value

    def __str__(self) -> str:
        """Get a string representation of `Game`."""
        return f"{self.url()} {self.perf_name} vs {self.opponent} ({self.id})"

    def __repr__(self) -> str:
        """Get a string representation of `Game`."""
        return self.__str__()


class Player:
    """Store information about a player."""

    def __init__(self, player_info: PlayerType) -> None:
        """:param player_info: Contains information about a player."""
        self.title = player_info.get("title")
        self.rating = player_info.get("rating")
        self.provisional = player_info.get("provisional")
        self.aiLevel = player_info.get("aiLevel")
        self.is_bot = self.title == "BOT" or self.aiLevel is not None
        self.name = f"AI level {self.aiLevel}" if self.aiLevel else player_info.get("name", "")

    def __str__(self) -> str:
        """Get a string representation of `Player`."""
        if self.aiLevel:
            return self.name
        rating = f'{self.rating}{"?" if self.provisional else ""}'
        return f'{self.title or ""} {self.name} ({rating})'.strip()

    def __repr__(self) -> str:
        """Get a string representation of `Player`."""
        return self.__str__()
