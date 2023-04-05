import random
import logging
import model
from timer import Timer
from collections import defaultdict
import lichess
import datetime
from config import Configuration, DelayType
from typing import Dict, Any, Set, Optional, Tuple, List, DefaultDict
USER_PROFILE_TYPE = Dict[str, Any]
EVENT_TYPE = Dict[str, Any]
MULTIPROCESSING_LIST_TYPE = List[model.Challenge]

logger = logging.getLogger(__name__)

daily_challenges_file_name = "daily_challenge_times.txt"
timestamp_format = "%Y-%m-%d %H:%M:%S\n"
one_day_seconds = datetime.timedelta(days=1).total_seconds()


def read_daily_challenges() -> List[Timer]:
    try:
        timers: List[Timer] = []
        with open(daily_challenges_file_name) as file:
            for line in file:
                timers.append(Timer(one_day_seconds, datetime.datetime.strptime(line, timestamp_format)))
    except FileNotFoundError:
        pass

    return [timer for timer in timers if not timer.is_expired()]


def write_daily_challenges(daily_challenges: List[Timer]) -> None:
    with open(daily_challenges_file_name, "w") as file:
        for timer in daily_challenges:
            file.write(timer.starting_timestamp().strftime(timestamp_format))


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
        self.daily_challenges: List[Timer] = read_daily_challenges()

        # (opponent name, game aspect) --> Timer
        # game aspect is the one the challenged bot objects to and is one of:
        #   - game speed (bullet, blitz, etc.)
        #   - variant (standard, horde, etc.)
        #   - casual/rated
        #   - opponent name (if no other reason is given)
        self.delay_timers: DefaultDict[Tuple[str, str], Timer] = defaultdict(Timer)
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
            logger.info(f"Challenge id {self.challenge_id} cancelled.")
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
            self.update_daily_challenge_record()
            self.last_challenge_created_delay.reset()
            response = self.li.challenge(username, params)
            challenge_id: str = response.get("challenge", {}).get("id", "")
            if not challenge_id:
                logger.error(response)
                self.add_to_block_list(username)
            return challenge_id
        except Exception as e:
            logger.warning("Could not create challenge")
            logger.debug(e, exc_info=e)
            self.show_earliest_challenge_time()
            return ""

    def update_daily_challenge_record(self) -> None:
        # As the number of challenges in a day increase, the minimum wait time between challenges increases.
        # 0   -  49 challenges --> 1 minute
        # 50  -  99 challenges --> 2 minutes
        # 100 - 149 challenges --> 3 minutes
        # etc.
        self.daily_challenges = [timer for timer in self.daily_challenges if not timer.is_expired()]
        self.daily_challenges.append(Timer(one_day_seconds))
        self.min_wait_time = 60 * ((len(self.daily_challenges) // 50) + 1)
        write_daily_challenges(self.daily_challenges)

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
            return all(timer.is_expired() for timer in self.get_delay_timers(bot["username"], variant, game_type, mode))

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
        self.challenge_id = challenge_id

    def game_done(self) -> None:
        self.last_game_ended_delay.reset()
        self.show_earliest_challenge_time()

    def show_earliest_challenge_time(self) -> None:
        postgame_timeout = self.last_game_ended_delay.time_until_expiration()
        time_to_next_challenge = self.min_wait_time - self.last_challenge_created_delay.time_since_reset()
        time_left = max(postgame_timeout, time_to_next_challenge)
        earliest_challenge_time = datetime.datetime.now() + datetime.timedelta(seconds=time_left)
        challenges = "challenge" + ("" if len(self.daily_challenges) == 1 else "s")
        logger.info(f"Next challenge will be created after {earliest_challenge_time.strftime('%X')} "
                    f"({len(self.daily_challenges)} {challenges} in last 24 hours)")

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
        decline_details: Dict[str, str] = {"generic": opponent.name,
                                           "later": opponent.name,
                                           "nobot": opponent.name,
                                           "toofast": challenge.speed,
                                           "tooslow": challenge.speed,
                                           "timecontrol": challenge.speed,
                                           "rated": mode,
                                           "casual": mode,
                                           "standard": challenge.variant,
                                           "variant": challenge.variant}

        reason_key = event["challenge"]["declineReasonKey"].lower()
        game_problem = decline_details[reason_key] if self.delay_type == DelayType.FINE else ""
        delay_timer = self.delay_timers[(opponent.name, game_problem)]
        delay_timer.duration += 3600
        delay_timer.reset()
        hours = "hours" if delay_timer.duration > 3600 else "hour"
        logger.info(f"Will not challenge {opponent} to a {game_problem}".strip()
                    + f" game for {int(delay_timer.duration/3600)} {hours}.")

        self.show_earliest_challenge_time()

    def get_delay_timers(self, opponent_name: str, variant: str, time_control: str, rated_mode: str) -> List[Timer]:
        aspects = [opponent_name, variant, time_control, rated_mode] if self.delay_type == DelayType.FINE else [opponent_name]
        return [self.delay_timers[(opponent_name, aspect)] for aspect in aspects]


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
