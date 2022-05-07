import random
import logging

logger = logging.getLogger(__name__)


class Matchmaking:
    def __init__(self, li, config):
        self.li = li
        self.variants = config["challenge"]["variants"].copy()
        if "fromPosition" in self.variants:
            self.variants.pop(self.variants.index("fromPosition"))
        self.matchmaking_cfg = config.get("matchmaking") or {}

    def create_challenge(self, username, base_time, increment, days, variant):
        mode = self.matchmaking_cfg.get("challenge_mode") or "random"
        if mode == "random":
            mode = random.choice(["casual", "rated"])
        rated = mode == "rated"
        params = {"rated": rated, "variant": variant}
        if days:
            params["days"] = days
        else:
            params["clock.limit"] = base_time
            params["clock.increment"] = increment
        challenge_id = self.li.challenge(username, params).get("challenge", {}).get("id")
        return challenge_id

    def choose_opponent(self):
        variant = random.choice(self.variants)
        base_time = self.matchmaking_cfg.get("challenge_initial_time") or 60
        increment = self.matchmaking_cfg.get("challenge_increment") or 2
        days = self.matchmaking_cfg.get("challenge_days")
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

        min_rating = self.matchmaking_cfg.get("opponent_min_rating") or 2000
        max_rating = self.matchmaking_cfg.get("opponent_max_rating") or 3000

        online_bots = self.li.get_online_bots()
        online_bots = list(filter(lambda bot: min_rating <= ((bot["perfs"].get(game_type) or {}).get("rating") or 0) <= max_rating, online_bots))
        bot_username = random.choice(online_bots)["username"] if online_bots else None
        return bot_username, base_time, increment, days, variant

    def challenge(self):
        bot_username, base_time, increment, days, variant = self.choose_opponent()
        logger.debug(f"Will challenge {bot_username} for a {variant} game.")
        challenge_id = self.create_challenge(bot_username, base_time, increment, days, variant) if bot_username else None
        logger.debug(f"Challenge id is {challenge_id}.")
        return challenge_id
