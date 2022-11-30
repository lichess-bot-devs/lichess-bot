import random
import logging
import model
from timer import Timer
from collections import defaultdict
from enum import Enum

logger = logging.getLogger(__name__)


class DelayType(str, Enum):
    NONE = "none"
    COARSE = "coarse"
    FINE = "fine"


class Matchmaking:
    def __init__(self, li, config, user_profile):
        self.li = li
        self.variants = list(filter(lambda variant: variant != "fromPosition", config["challenge"]["variants"]))
        self.matchmaking_cfg = config.get("matchmaking") or {}
        self.user_profile = user_profile
        self.last_challenge_created_delay = Timer(25)  # The challenge expires 20 seconds after creating it.
        self.last_game_ended_delay = Timer(max(self.matchmaking_cfg.get("challenge_timeout") or 30, 1) * 60)
        self.last_user_profile_update_time = Timer(5 * 60)  # 5 minutes
        self.min_wait_time = 60  # Wait 60 seconds before creating a new challenge to avoid hitting the api rate limits.
        self.challenge_id = None
        self.block_list = (self.matchmaking_cfg.get("block_list") or []).copy()
        self.delay_timers = defaultdict(lambda: Timer(0))
        delay_option = "delay_after_decline"
        self.delay_type = self.matchmaking_cfg.get(delay_option) or DelayType.NONE
        if self.delay_type not in DelayType.__members__.values():
            raise ValueError(f"{self.delay_type} is not a valid value for {delay_option} parameter."
                             f" Choices are: {', '.join(DelayType)}.")

    def should_create_challenge(self):
        matchmaking_enabled = self.matchmaking_cfg.get("allow_matchmaking")
        time_has_passed = self.last_game_ended_delay.is_expired()
        challenge_expired = self.last_challenge_created_delay.is_expired() and self.challenge_id
        min_wait_time_passed = self.last_challenge_created_delay.time_since_reset() > self.min_wait_time
        if challenge_expired:
            self.li.cancel(self.challenge_id)
            logger.debug(f"Challenge id {self.challenge_id} cancelled.")
            self.challenge_id = None
        return matchmaking_enabled and (time_has_passed or challenge_expired) and min_wait_time_passed

    def create_challenge(self, username, base_time, increment, days, variant, mode):
        params = {"rated": mode == "rated", "variant": variant}

        if days:
            params["days"] = days
        elif base_time or increment:
            params["clock.limit"] = base_time
            params["clock.increment"] = increment
        else:
            logger.error("At least one of challenge_days, challenge_initial_time, or challenge_increment "
                         "must be greater than zero in the matchmaking section of your config file.")
            return None

        try:
            response = self.li.challenge(username, params)
            challenge_id = response.get("challenge", {}).get("id")
            if not challenge_id:
                logger.error(response)
                self.add_to_block_list(username)
            return challenge_id
        except Exception:
            logger.exception("Could not create challenge")
            return None

    def get_time(self, name, default=None):
        match_time = self.matchmaking_cfg.get(name, default)
        if match_time is None:
            return None
        if isinstance(match_time, int):
            match_time = [match_time]
        return random.choice(match_time)

    def perf(self):
        return self.user_profile["perfs"]

    def username(self):
        return self.user_profile["username"]

    def update_user_profile(self):
        if self.last_user_profile_update_time.is_expired():
            self.last_user_profile_update_time.reset()
            self.user_profile = self.li.get_profile()

    def choose_opponent(self):
        variant = self.get_random_config_value("challenge_variant", self.variants)
        mode = self.get_random_config_value("challenge_mode", ["casual", "rated"])

        base_time = self.get_time("challenge_initial_time", 60)
        increment = self.get_time("challenge_increment", 2)
        days = self.get_time("challenge_days")

        play_correspondence = [bool(days), not bool(base_time or increment)]
        if random.choice(play_correspondence):
            base_time = 0
            increment = 0
        else:
            days = 0

        game_type = game_category(variant, base_time, increment, days)

        min_rating = self.matchmaking_cfg.get("opponent_min_rating") or 600
        max_rating = self.matchmaking_cfg.get("opponent_max_rating") or 4000
        rating_diff = self.matchmaking_cfg.get("opponent_rating_difference")
        if rating_diff is not None:
            bot_rating = self.perf().get(game_type, {}).get("rating", 0)
            min_rating = bot_rating - rating_diff
            max_rating = bot_rating + rating_diff
        logger.info(f"Seeking {game_type} game with opponent rating in [{min_rating}, {max_rating}] ...")
        allow_tos_violation = self.matchmaking_cfg.get("opponent_allow_tos_violation", True)

        def is_suitable_opponent(bot):
            perf = bot.get("perfs", {}).get(game_type, {})
            return (bot["username"] != self.username()
                    and bot["username"] not in self.block_list
                    and not bot.get("disabled")
                    and (allow_tos_violation or not bot.get("tosViolation"))  # Terms of Service
                    and perf.get("games", 0) > 0
                    and min_rating <= perf.get("rating", 0) <= max_rating)

        online_bots = self.li.get_online_bots()
        online_bots = list(filter(is_suitable_opponent, online_bots))

        def ready_for_challenge(bot):
            return self.get_delay_timer(bot["username"], variant, game_type, mode).is_expired()

        ready_bots = list(filter(ready_for_challenge, online_bots))
        online_bots = ready_bots or online_bots

        try:
            bot_username = None
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

    def get_random_config_value(self, parameter, choices):
        value = self.matchmaking_cfg.get(parameter) or "random"
        return value if value != "random" else random.choice(choices)

    def challenge(self, active_games, challenge_queue):
        if active_games or challenge_queue or not self.should_create_challenge():
            return

        logger.info("Challenging a random bot")
        self.update_user_profile()
        bot_username, base_time, increment, days, variant, mode = self.choose_opponent()
        logger.info(f"Will challenge {bot_username} for a {variant} game.")
        challenge_id = self.create_challenge(bot_username, base_time, increment, days, variant, mode) if bot_username else None
        logger.info(f"Challenge id is {challenge_id}.")
        self.last_challenge_created_delay.reset()
        self.challenge_id = challenge_id

    def add_to_block_list(self, username):
        logger.info(f"Will not challenge {username} again during this session.")
        self.block_list.append(username)

    def declined_challenge(self, event):
        challenge = model.Challenge(event["challenge"], self.user_profile)
        opponent = event["challenge"]["destUser"]["name"]
        reason = event["challenge"]["declineReason"]
        logger.info(f"{opponent} declined {challenge}: {reason}")
        if not challenge.from_self or self.delay_type == DelayType.NONE:
            return

        # Add one hour to delay each time a challenge is declined.
        mode = "rated" if challenge.rated else "casual"
        delay_timer = self.get_delay_timer(opponent,
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

    def get_delay_timer(self, opponent_name, variant, time_control, rated_mode):
        if self.delay_type == DelayType.FINE:
            return self.delay_timers[(opponent_name, variant, time_control, rated_mode)]
        else:
            return self.delay_timers[opponent_name]


def game_category(variant, base_time, increment, days):
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
