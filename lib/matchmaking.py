"""Challenge other bots."""
import random
import logging
import datetime
import contextlib
from lib import model
from lib.timer import Timer, seconds, minutes, days, years
from collections import defaultdict
from collections.abc import Sequence
from lib.lichess import Lichess
from lib.config import Configuration
from typing import Optional, Union
from lib.lichess_types import UserProfileType, PerfType, EventType, FilterType
MULTIPROCESSING_LIST_TYPE = Sequence[model.Challenge]
DAILY_TIMERS_TYPE = list[Timer]

logger = logging.getLogger(__name__)

daily_challenges_file_name = "daily_challenge_times.txt"
timestamp_format = "%Y-%m-%d %H:%M:%S\n"


def read_daily_challenges() -> DAILY_TIMERS_TYPE:
    """Read the challenges we have created in the past 24 hours from a text file."""
    timers: DAILY_TIMERS_TYPE = []
    try:
        with open(daily_challenges_file_name) as file:
            for line in file:
                timers.append(Timer(days(1), datetime.datetime.strptime(line, timestamp_format)))
    except FileNotFoundError:
        pass

    return [timer for timer in timers if not timer.is_expired()]


def write_daily_challenges(daily_challenges: DAILY_TIMERS_TYPE) -> None:
    """Write the challenges we have created in the past 24 hours to a text file."""
    with open(daily_challenges_file_name, "w") as file:
        for timer in daily_challenges:
            file.write(timer.starting_timestamp(timestamp_format))


class Matchmaking:
    """Challenge other bots."""

    def __init__(self, li: Lichess, config: Configuration, user_profile: UserProfileType) -> None:
        """Initialize values needed for matchmaking."""
        self.li = li
        self.variants = list(filter(lambda variant: variant != "fromPosition", config.challenge.variants))
        self.matchmaking_cfg = config.matchmaking
        self.user_profile = user_profile
        self.last_challenge_created_delay = Timer(seconds(25))  # Challenges expire after 20 seconds.
        self.last_game_ended_delay = Timer(minutes(self.matchmaking_cfg.challenge_timeout))
        self.last_user_profile_update_time = Timer(minutes(5))
        self.min_wait_time = seconds(60)  # Wait before new challenge to avoid api rate limits.

        # Maximum time between challenges, even if there are active games
        self.max_wait_time = minutes(10) if self.matchmaking_cfg.allow_during_games else years(10)
        self.challenge_id = ""
        self.daily_challenges = read_daily_challenges()

        # (opponent name, game aspect) --> other bot is likely to accept challenge
        # game aspect is the one the challenged bot objects to and is one of:
        #   - game speed (bullet, blitz, etc.)
        #   - variant (standard, horde, etc.)
        #   - casual/rated
        #   - empty string (if no other reason is given or self.filter_type is COARSE)
        self.challenge_type_acceptable: defaultdict[tuple[str, str], bool] = defaultdict(lambda: True)
        self.challenge_filter = self.matchmaking_cfg.challenge_filter

        for name in self.matchmaking_cfg.block_list:
            self.add_to_block_list(name)

    def should_create_challenge(self) -> bool:
        """Whether we should create a challenge."""
        matchmaking_enabled = self.matchmaking_cfg.allow_matchmaking
        time_has_passed = self.last_game_ended_delay.is_expired()
        challenge_expired = self.last_challenge_created_delay.is_expired() and self.challenge_id
        min_wait_time_passed = self.last_challenge_created_delay.time_since_reset() > self.min_wait_time
        if challenge_expired:
            self.li.cancel(self.challenge_id)
            logger.info(f"Challenge id {self.challenge_id} cancelled.")
            self.discard_challenge(self.challenge_id)
            self.show_earliest_challenge_time()
        return bool(matchmaking_enabled and (time_has_passed or challenge_expired) and min_wait_time_passed)

    def create_challenge(self, username: str, base_time: int, increment: int, days: int, variant: str,
                         mode: str) -> str:
        """Create a challenge."""
        params: dict[str, Union[str, int, bool]] = {"rated": mode == "rated", "variant": variant}

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
            challenge_id = response.get("id", "")
            if not challenge_id:
                logger.error(response)
                self.add_to_block_list(username)
                self.show_earliest_challenge_time()
            return challenge_id
        except Exception as e:
            logger.warning("Could not create challenge")
            logger.debug(e, exc_info=e)
            self.show_earliest_challenge_time()
            return ""

    def update_daily_challenge_record(self) -> None:
        """
        Record timestamp of latest challenge and update minimum wait time.

        As the number of challenges in a day increase, the minimum wait time between challenges increases.
        0   -  49 challenges --> 1 minute
        50  -  99 challenges --> 2 minutes
        100 - 149 challenges --> 3 minutes
        etc.
        """
        self.daily_challenges = [timer for timer in self.daily_challenges if not timer.is_expired()]
        self.daily_challenges.append(Timer(days(1)))
        self.min_wait_time = seconds(60) * ((len(self.daily_challenges) // 50) + 1)
        write_daily_challenges(self.daily_challenges)

    def perf(self) -> dict[str, PerfType]:
        """Get the bot's rating in every variant. Bullet, blitz, rapid etc. are considered different variants."""
        user_perf: dict[str, PerfType] = self.user_profile["perfs"]
        return user_perf

    def username(self) -> str:
        """Our username."""
        username: str = self.user_profile["username"]
        return username

    def update_user_profile(self) -> None:
        """Update our user profile data, to get our latest rating."""
        if self.last_user_profile_update_time.is_expired():
            self.last_user_profile_update_time.reset()
            with contextlib.suppress(Exception):
                self.user_profile = self.li.get_profile()

    def get_weights(self, online_bots: list[UserProfileType], rating_preference: str, min_rating: int, max_rating: int,
                    game_type: str) -> list[int]:
        """Get the weight for each bot. A higher weights means the bot is more likely to get challenged."""
        def rating(bot: UserProfileType) -> int:
            perfs: dict[str, PerfType] = bot.get("perfs", {})
            perf: PerfType = perfs.get(game_type, {})
            return perf.get("rating", 0)

        if rating_preference == "high":
            # A bot with max_rating rating will be twice as likely to get picked than a bot with min_rating rating.
            reduce_ratings_by = min(min_rating - (max_rating - min_rating), min_rating - 1)
            weights = [rating(bot) - reduce_ratings_by for bot in online_bots]
        elif rating_preference == "low":
            # A bot with min_rating rating will be twice as likely to get picked than a bot with max_rating rating.
            reduce_ratings_by = max(max_rating - (min_rating - max_rating), max_rating + 1)
            weights = [reduce_ratings_by - rating(bot) for bot in online_bots]
        else:
            weights = [1] * len(online_bots)
        return weights

    def choose_opponent(self) -> tuple[Optional[str], int, int, int, str, str]:
        """Choose an opponent."""
        override_choice = random.choice(self.matchmaking_cfg.overrides.keys() + [None])
        logger.info(f"Using the {override_choice or 'default'} matchmaking configuration.")
        override = {} if override_choice is None else self.matchmaking_cfg.overrides.lookup(override_choice)
        match_config = self.matchmaking_cfg | override

        variant = self.get_random_config_value(match_config, "challenge_variant", self.variants)
        mode = self.get_random_config_value(match_config, "challenge_mode", ["casual", "rated"])
        rating_preference = match_config.rating_preference

        base_time = random.choice(match_config.challenge_initial_time)
        increment = random.choice(match_config.challenge_increment)
        days = random.choice(match_config.challenge_days)

        play_correspondence = [bool(days), not bool(base_time or increment)]
        if random.choice(play_correspondence):
            base_time = 0
            increment = 0
        else:
            days = 0

        game_type = game_category(variant, base_time, increment, days)

        min_rating = match_config.opponent_min_rating
        max_rating = match_config.opponent_max_rating
        rating_diff = match_config.opponent_rating_difference
        bot_rating = self.perf().get(game_type, {}).get("rating", 0)
        if rating_diff is not None and bot_rating > 0:
            min_rating = bot_rating - rating_diff
            max_rating = bot_rating + rating_diff
        logger.info(f"Seeking {game_type} game with opponent rating in [{min_rating}, {max_rating}] ...")
        allow_tos_violation = match_config.opponent_allow_tos_violation

        def is_suitable_opponent(bot: UserProfileType) -> bool:
            perf = bot.get("perfs", {}).get(game_type, {})
            return (bot["username"] != self.username()
                    and not self.in_block_list(bot["username"])
                    and not bot.get("disabled")
                    and (allow_tos_violation or not bot.get("tosViolation"))  # Terms of Service violation.
                    and perf.get("games", 0) > 0
                    and min_rating <= perf.get("rating", 0) <= max_rating)

        online_bots = self.li.get_online_bots()
        online_bots = list(filter(is_suitable_opponent, online_bots))

        def ready_for_challenge(bot: UserProfileType) -> bool:
            aspects = [variant, game_type, mode] if self.challenge_filter == FilterType.FINE else []
            return all(self.should_accept_challenge(bot["username"], aspect) for aspect in aspects)

        ready_bots = list(filter(ready_for_challenge, online_bots))
        online_bots = ready_bots or online_bots
        bot_username = None
        weights = self.get_weights(online_bots, rating_preference, min_rating, max_rating, game_type)

        try:
            bot = random.choices(online_bots, weights=weights)[0]
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

    def get_random_config_value(self, config: Configuration, parameter: str, choices: list[str]) -> str:
        """Choose a random value from `choices` if the parameter value in the config is `random`."""
        value: str = config.lookup(parameter)
        return value if value != "random" else random.choice(choices)

    def challenge(self, active_games: set[str], challenge_queue: MULTIPROCESSING_LIST_TYPE, max_games: int) -> None:
        """
        Challenge an opponent.

        :param active_games: The games that the bot is playing.
        :param challenge_queue: The queue containing the challenges.
        :param max_games: The maximum allowed number of simultaneous games.
        """
        max_games_for_matchmaking = max_games if self.matchmaking_cfg.allow_during_games else min(1, max_games)
        game_count = len(active_games) + len(challenge_queue)
        if (game_count >= max_games_for_matchmaking
                or (game_count > 0 and self.last_challenge_created_delay.time_since_reset() < self.max_wait_time)
                or not self.should_create_challenge()):
            return

        logger.info("Challenging a random bot")
        self.update_user_profile()
        bot_username, base_time, increment, days, variant, mode = self.choose_opponent()
        logger.info(f"Will challenge {bot_username} for a {variant} game.")
        challenge_id = self.create_challenge(bot_username, base_time, increment, days, variant, mode) if bot_username else ""
        logger.info(f"Challenge id is {challenge_id if challenge_id else 'None'}.")
        self.challenge_id = challenge_id

    def discard_challenge(self, challenge_id: str) -> None:
        """
        Clear the ID of the most recent challenge if it is no longer needed.

        :param challenge_id: The ID of the challenge that is expired, accepted, or declined.
        """
        if self.challenge_id == challenge_id:
            self.challenge_id = ""

    def game_done(self) -> None:
        """Reset the timer for when the last game ended, and prints the earliest that the next challenge will be created."""
        self.last_game_ended_delay.reset()
        self.show_earliest_challenge_time()

    def show_earliest_challenge_time(self) -> None:
        """Show the earliest that the next challenge will be created."""
        if self.matchmaking_cfg.allow_matchmaking:
            postgame_timeout = self.last_game_ended_delay.time_until_expiration()
            time_to_next_challenge = self.min_wait_time - self.last_challenge_created_delay.time_since_reset()
            time_left = max(postgame_timeout, time_to_next_challenge)
            earliest_challenge_time = datetime.datetime.now() + time_left
            challenges = "challenge" + ("" if len(self.daily_challenges) == 1 else "s")
            logger.info(f"Next challenge will be created after {earliest_challenge_time.strftime('%X')} "
                        f"({len(self.daily_challenges)} {challenges} in last 24 hours)")

    def add_to_block_list(self, username: str) -> None:
        """Add a bot to the blocklist."""
        self.add_challenge_filter(username, "")

    def in_block_list(self, username: str) -> bool:
        """Check if an opponent is in the block list to prevent future challenges."""
        return not self.should_accept_challenge(username, "")

    def add_challenge_filter(self, username: str, game_aspect: str) -> None:
        """
        Prevent creating another challenge when an opponent has decline a challenge.

        :param username: The name of the opponent.
        :param game_aspect: The aspect of a game (time control, chess variant, etc.)
        that caused the opponent to decline a challenge. If the parameter is empty,
        that is equivalent to adding the opponent to the block list.
        """
        self.challenge_type_acceptable[(username, game_aspect)] = False

    def should_accept_challenge(self, username: str, game_aspect: str) -> bool:
        """
        Whether a bot is likely to accept a challenge to a game.

        :param username: The name of the opponent.
        :param game_aspect: A category of the challenge type (time control, chess variant, etc.) to test for acceptance.
        If game_aspect is empty, this is equivalent to checking if the opponent is in the block list.
        """
        return self.challenge_type_acceptable[(username, game_aspect)]

    def accepted_challenge(self, event: EventType) -> None:
        """
        Set the challenge id to an empty string, if the challenge was accepted.

        Otherwise, we would attempt to cancel the challenge later.
        """
        self.discard_challenge(event["game"]["id"])

    def declined_challenge(self, event: EventType) -> None:
        """
        Handle a challenge that was declined by the opponent.

        Depends on whether `FilterType` is `NONE`, `COARSE`, or `FINE`.
        """
        challenge = model.Challenge(event["challenge"], self.user_profile)
        opponent = challenge.challenge_target
        reason = event["challenge"]["declineReason"]
        logger.info(f"{opponent} declined {challenge}: {reason}")
        self.discard_challenge(challenge.id)
        if not challenge.from_self or self.challenge_filter == FilterType.NONE:
            return

        mode = "rated" if challenge.rated else "casual"
        decline_details: dict[str, str] = {"generic": "",
                                           "later": "",
                                           "nobot": "",
                                           "toofast": challenge.speed,
                                           "tooslow": challenge.speed,
                                           "timecontrol": challenge.speed,
                                           "rated": mode,
                                           "casual": mode,
                                           "standard": challenge.variant,
                                           "variant": challenge.variant}

        reason_key = event["challenge"]["declineReasonKey"].lower()
        if reason_key not in decline_details:
            logger.warning(f"Unknown decline reason received: {reason_key}")
        game_problem = decline_details.get(reason_key, "") if self.challenge_filter == FilterType.FINE else ""
        self.add_challenge_filter(opponent.name, game_problem)
        logger.info(f"Will not challenge {opponent} to another {game_problem}".strip() + " game.")

        self.show_earliest_challenge_time()


def game_category(variant: str, base_time: int, increment: int, days: int) -> str:
    """
    Get the game type (e.g. bullet, atomic, classical). Lichess has one rating for every variant regardless of time control.

    :param variant: The game's variant.
    :param base_time: The base time in seconds.
    :param increment: The increment in seconds.
    :param days: If the game is correspondence, we have some days to play the move.
    :return: The game category.
    """
    game_duration = base_time + increment * 40
    if variant != "standard":
        return variant
    if days:
        return "correspondence"
    if game_duration < 179:
        return "bullet"
    if game_duration < 479:
        return "blitz"
    if game_duration < 1499:
        return "rapid"
    return "classical"
