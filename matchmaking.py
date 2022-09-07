import random
import time
import logging

logger = logging.getLogger(__name__)


class Matchmaking:
    def __init__(self, li, config, user_profile):
        self.li = li
        self.variants = list(filter(lambda variant: variant != "fromPosition", config["challenge"]["variants"]))
        self.matchmaking_cfg = config.get("matchmaking") or {}
        self.user_profile = user_profile
        self.user_profile_update_interval = 5 * 60  # 5 minutes
        self.last_user_profile_update = time.time()
        self.last_challenge_created = time.time()
        self.last_game_ended = time.time()
        self.challenge_expire_time = 25  # The challenge expires 20 seconds after creating it.
        self.challenge_timeout = max(self.matchmaking_cfg.get("challenge_timeout") or 30, 1) * 60
        self.min_wait_time = 60  # Wait 60 seconds before creating a new challenge to avoid hitting the api rate limits.
        self.challenge_id = None
        self.block_list = []

    def should_create_challenge(self):
        matchmaking_enabled = self.matchmaking_cfg.get("allow_matchmaking")
        time_has_passed = self.last_game_ended + self.challenge_timeout < time.time()
        challenge_expired = self.last_challenge_created + self.challenge_expire_time < time.time() and self.challenge_id
        min_wait_time_passed = self.last_challenge_created + self.min_wait_time < time.time()
        if challenge_expired:
            self.li.cancel(self.challenge_id)
            logger.debug(f"Challenge id {self.challenge_id} cancelled.")
            self.challenge_id = None
        return matchmaking_enabled and (time_has_passed or challenge_expired) and min_wait_time_passed

    def create_challenge(self, username, base_time, increment, days, variant):
        mode = self.matchmaking_cfg.get("challenge_mode") or "random"
        if mode == "random":
            mode = random.choice(["casual", "rated"])
        rated = mode == "rated"
        params = {"rated": rated, "variant": variant}

        play_correspondence = []
        if days:
            play_correspondence.append(True)

        if base_time or increment:
            play_correspondence.append(False)

        if random.choice(play_correspondence):
            params["days"] = days
        else:
            params["clock.limit"] = base_time
            params["clock.increment"] = increment

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
        if time.time() > self.last_user_profile_update + self.user_profile_update_interval:
            self.last_user_profile_update = time.time()
            self.user_profile = self.li.get_profile()

    def choose_opponent(self):
        variant = self.matchmaking_cfg.get("challenge_variant") or "random"
        if variant == "random":
            variant = random.choice(self.variants)

        base_time = self.get_time("challenge_initial_time", 60)
        increment = self.get_time("challenge_increment", 2)
        days = self.get_time("challenge_days")
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

        return bot_username, base_time, increment, days, variant

    def challenge(self):
        self.update_user_profile()
        bot_username, base_time, increment, days, variant = self.choose_opponent()
        logger.info(f"Will challenge {bot_username} for a {variant} game.")
        challenge_id = self.create_challenge(bot_username, base_time, increment, days, variant) if bot_username else None
        logger.info(f"Challenge id is {challenge_id}.")
        self.last_challenge_created = time.time()
        self.challenge_id = challenge_id

    def add_to_block_list(self, username):
        logger.info(f"Will not challenge {username} again during this session.")
        self.block_list.append(username)


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
