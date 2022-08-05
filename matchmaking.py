import random
import time
import logging

logger = logging.getLogger(__name__)


class Matchmaking:
    def __init__(self, li, config, username):
        self.li = li
        self.variants = list(filter(lambda variant: variant != "fromPosition", config["challenge"]["variants"]))
        self.matchmaking_cfg = config.get("matchmaking") or {}
        self.username = username
        self.last_challenge_created = time.time()
        self.last_game_ended = time.time()
        self.challenge_expire_time = 25  # The challenge expires 20 seconds after creating it.
        self.challenge_timeout = max(self.matchmaking_cfg.get("challenge_timeout") or 30, 1) * 60
        self.min_wait_time = 60  # Wait 60 seconds before creating a new challenge to avoid hitting the api rate limits.
        self.challenge_id = None

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

    def choose_opponent(self):
        variant = self.matchmaking_cfg.get("challenge_variant") or "random"
        if variant == "random":
            variant = random.choice(self.variants)

        base_time = self.get_time("challenge_initial_time", 60)
        increment = self.get_time("challenge_increment", 2)
        days = self.get_time("challenge_days")

        game_duration = base_time + increment * 40
        if variant != "standard":
            game_type = variant
        elif days:
            game_type = "correspondence"
        elif game_duration < 179:
            game_type = "bullet"
        elif game_duration < 479:
            game_type = "blitz"
        elif game_duration < 1499:
            game_type = "rapid"
        else:
            game_type = "classical"

        min_rating = self.matchmaking_cfg.get("opponent_min_rating") or 600
        max_rating = self.matchmaking_cfg.get("opponent_max_rating") or 4000

        def is_suitable_opponent(bot):
            perf = bot["perfs"].get(game_type, {})
            return (bot["username"] != self.username
                    and not bot.get("disabled")
                    and perf.get("games", 0) > 0
                    and min_rating <= perf.get("rating", 0) <= max_rating)

        online_bots = self.li.get_online_bots()
        online_bots = list(filter(is_suitable_opponent, online_bots))

        bot_username = random.choice(online_bots)["username"] if online_bots else None
        return bot_username, base_time, increment, days, variant

    def challenge(self):
        bot_username, base_time, increment, days, variant = self.choose_opponent()
        logger.info(f"Will challenge {bot_username} for a {variant} game.")
        challenge_id = self.create_challenge(bot_username, base_time, increment, days, variant) if bot_username else None
        logger.info(f"Challenge id is {challenge_id}.")
        self.last_challenge_created = time.time()
        self.challenge_id = challenge_id
