import random
import logging
import model
from timer import Timer
from collections import defaultdict
import lichess
from config import Configuration, DelayType
from typing import Dict, Any, Set, Optional, Tuple, List, DefaultDict, Union
USER_PROFILE_TYPE = Dict[str, Any]
EVENT_TYPE = Dict[str, Any]
MULTIPROCESSING_LIST_TYPE = List[model.Challenge]

logger = logging.getLogger(__name__)


class Matchmaking:
    def __init__(self, li: lichess.Lichess, config: Configuration, user_profile: USER_PROFILE_TYPE) -> None:
        self.li = li
        self.variants = list(filter(lambda variant: variant != "fromPosition", config.challenge.variants))
        self.matchmaking_cfg = config.matchmaking
        self.user_profile = user_profile
        self.last_challenge_created_delay = Timer(25)  # The challenge expires 20 seconds after creating it.
        self.last_game_ended_delay = Timer(self.matchmaking_cfg.challenge_timeout * 60)
        self.last_user_profile_update_time = Timer(5 * 60)  # 5 minutes
        self.min_wait_time = 60  # Wait 60 seconds before creating a new challenge to avoid hitting the api rate limits.
        self.challenge_id: str = ""
        self.block_list = self.matchmaking_cfg.block_list.copy()
        self.delay_timers: DefaultDict[Union[str, Tuple[str, str, str, str]], Timer] = defaultdict(Timer)
        delay_option = "delay_after_decline"
        self.delay_type = self.matchmaking_cfg.lookup(delay_option)
        if self.delay_type not in DelayType.__members__.values():
            raise ValueError(f"{self.delay_type} is not a valid value for {delay_option} parameter."
                             f" Choices are: {', '.join(DelayType)}.")

    def should_create_challenge(self) -> bool:
        matchmaking_enabled = self.matchmaking_cfg.allow_matchmaking
        time_has_passed = self.last_game_ended_delay.is_expired()
        challenge_expired = self.last_challenge_created_delay.is_expired() and self.challenge_id
        min_wait_time_passed = self.last_challenge_created_delay.time_since_reset() > self.min_wait_time
        if challenge_expired:
            self.li.cancel(self.challenge_id)
            logger.debug(f"Challenge id {self.challenge_id} cancelled.")
            self.challenge_id = ""
        return bool(matchmaking_enabled and (time_has_passed or challenge_expired) and min_wait_time_passed)

    def create_challenge(self, username: str, base_time: int, increment: int, days: int, variant: str,
                         mode: str) -> str:
        params = {"rated": mode == "rated", "variant": variant}

        if days:
            params["days"] = days
        elif base_time or increment:
            params["clock.limit"] = base_time
            params["clock.increment"] = increment
        else:
            logger.error("At least one of challenge_days, challenge_initial_time, or challenge_increment "
                         "must be greater than zero in the matchmaking section of your config file.")
            return ""

        try:
            response = self.li.challenge(username, params)
            challenge_id: str = response.get("challenge", {}).get("id", "")
            if not challenge_id:
                logger.error(response)
                self.add_to_block_list(username)
            return challenge_id
        except Exception:
            logger.exception("Could not create challenge")
            return ""

    def perf(self) -> Dict[str, Dict[str, Any]]:
        user_perf: Dict[str, Dict[str, Any]] = self.user_profile["perfs"]
        return user_perf

    def username(self) -> str:
        username: str = self.user_profile["username"]
        return username

    def update_user_profile(self) -> None:
        if self.last_user_profile_update_time.is_expired():
            self.last_user_profile_update_time.reset()
            try:
                self.user_profile = self.li.get_profile()
            except Exception:
                pass

    def choose_opponent(self) -> Tuple[Optional[str], int, int, int, str, str]:
        variant = self.get_random_config_value("challenge_variant", self.variants)
        mode = self.get_random_config_value("challenge_mode", ["casual", "rated"])

        base_time = random.choice(self.matchmaking_cfg.challenge_initial_time)
        increment = random.choice(self.matchmaking_cfg.challenge_increment)
        days = random.choice(self.matchmaking_cfg.challenge_days)

        play_correspondence = [bool(days), not bool(base_time or increment)]
        if random.choice(play_correspondence):
            base_time = 0
            increment = 0
        else:
            days = 0

        game_type = game_category(variant, base_time, increment, days)

        min_rating = self.matchmaking_cfg.opponent_min_rating
        max_rating = self.matchmaking_cfg.opponent_max_rating
        rating_diff = self.matchmaking_cfg.opponent_rating_difference
        bot_rating = self.perf().get(game_type, {}).get("rating", 0)
        if rating_diff is not None and bot_rating > 0:
            min_rating = bot_rating - rating_diff
            max_rating = bot_rating + rating_diff
        logger.info(f"Seeking {game_type} game with opponent rating in [{min_rating}, {max_rating}] ...")
        allow_tos_violation = self.matchmaking_cfg.opponent_allow_tos_violation

        def is_suitable_opponent(bot: USER_PROFILE_TYPE) -> bool:
            perf = bot.get("perfs", {}).get(game_type, {})
            return (bot["username"] != self.username()
                    and bot["username"] not in self.block_list
                    and not bot.get("disabled")
                    and (allow_tos_violation or not bot.get("tosViolation"))  # Terms of Service
                    and perf.get("games", 0) > 0
                    and min_rating <= perf.get("rating", 0) <= max_rating)

        online_bots = self.li.get_online_bots()
        online_bots = list(filter(is_suitable_opponent, online_bots))

        def ready_for_challenge(bot: USER_PROFILE_TYPE) -> bool:
            return self.get_delay_timer(bot["username"], variant, game_type, mode).is_expired()

        ready_bots = list(filter(ready_for_challenge, online_bots))
        online_bots = ready_bots or online_bots
        bot_username = None

        try:
            bot = random.choice(online_bots)
            bot_profile = self.li.get_public_data(bot["username"])
            if bot_profile.get("blocking"):
                self.add_to_block_list(bot["username"])
            else:
                bot_username = bot["username"]
        except Exception:
            if online_bots:
                logger.exception("Error:")
            else:
                logger.error("No suitable bots found to challenge.")

        return bot_username, base_time, increment, days, variant, mode

    def get_random_config_value(self, parameter: str, choices: List[str]) -> str:
        value: str = self.matchmaking_cfg.lookup(parameter)
        return value if value != "random" else random.choice(choices)

    def challenge(self, active_games: Set[str], challenge_queue: MULTIPROCESSING_LIST_TYPE) -> None:
        if active_games or challenge_queue or not self.should_create_challenge():
            return

        logger.info("Challenging a random bot")
        self.update_user_profile()
        bot_username, base_time, increment, days, variant, mode = self.choose_opponent()
        logger.info(f"Will challenge {bot_username} for a {variant} game.")
        challenge_id = self.create_challenge(bot_username, base_time, increment, days, variant, mode) if bot_username else ""
        logger.info(f"Challenge id is {challenge_id if challenge_id else 'None'}.")
        self.last_challenge_created_delay.reset()
        self.challenge_id = challenge_id

    def add_to_block_list(self, username: str) -> None:
        logger.info(f"Will not challenge {username} again during this session.")
        self.block_list.append(username)

    def accepted_challenge(self, event: EVENT_TYPE) -> None:
        if self.challenge_id == event["game"]["id"]:
            self.challenge_id = ""

    def declined_challenge(self, event: EVENT_TYPE) -> None:
        challenge = model.Challenge(event["challenge"], self.user_profile)
        opponent = challenge.opponent
        reason = event["challenge"]["declineReason"]
        logger.info(f"{opponent} declined {challenge}: {reason}")
        if self.challenge_id == challenge.id:
            self.challenge_id = ""
        if not challenge.from_self or self.delay_type == DelayType.NONE:
            return

        # Add one hour to delay each time a challenge is declined.
        mode = "rated" if challenge.rated else "casual"
        delay_timer = self.get_delay_timer(opponent.name,
                                           challenge.variant,
                                           challenge.speed,
                                           mode)
        delay_timer.duration += 3600
        delay_timer.reset()
        hours = "hours" if delay_timer.duration > 3600 else "hour"
        if self.delay_type == DelayType.FINE:
            logger.info(f"Will not challenge {opponent} to a {mode} {challenge.speed} "
                        f"{challenge.variant} game for {int(delay_timer.duration/3600)} {hours}.")
        else:
            logger.info(f"Will not challenge {opponent} for {int(delay_timer.duration/3600)} {hours}.")

    def get_delay_timer(self, opponent_name: str, variant: str, time_control: str, rated_mode: str) -> Timer:
        if self.delay_type == DelayType.FINE:
            return self.delay_timers[(opponent_name, variant, time_control, rated_mode)]
        else:
            return self.delay_timers[opponent_name]


def game_category(variant: str, base_time: int, increment: int, days: int) -> str:
    game_duration = base_time + increment * 40
    if variant != "standard":
        return variant
    elif days:
        return "correspondence"
    elif game_duration < 179:
        return "bullet"
    elif game_duration < 479:
        return "blitz"
    elif game_duration < 1499:
        return "rapid"
    else:
        return "classical"
