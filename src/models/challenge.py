class Challenge:
    RATED = "rated"
    CASUAL = "casual"
    ANONYMOUS = "Anonymous"
    BOT_TITLE = "BOT"
    SCORE_BOOST = 200

    def __init__(self, c_info):
        self.id = c_info["id"]
        self.rated = c_info["rated"]
        self.variant = c_info["variant"]["key"]
        self.perf_name = c_info["perf"]["name"]
        self.speed = c_info["speed"]
        self.increment = c_info.get("timeControl", {}).get("increment", -1)
        self.challenger = c_info.get("challenger")
        self.challenger_title = self.challenger.get("title") if self.challenger else None
        self.challenger_is_bot = self.challenger_title == Challenge.BOT_TITLE
        self.challenger_master_title = self.challenger_title if not self.challenger_is_bot else None
        self.challenger_name = self.challenger["name"] if self.challenger else Challenge.ANONYMOUS
        self.challenger_rating_int = self.challenger["rating"] if self.challenger else 0
        self.challenger_rating = self.challenger_rating_int or "?"

    def is_supported_variant(self, supported):
        return self.variant in supported

    def is_supported_time_control(self, supported_speed, supported_increment_max, supported_increment_min):
        if self.increment < 0:
            return self.speed in supported_speed

        return self.speed in supported_speed and supported_increment_min <= self.increment <= supported_increment_max

    def is_supported_mode(self, supported):
        return "rated" in supported if self.rated else "casual" in supported

    def is_supported(self, config):
        if not config.get("accept_bot", False) and self.challenger_is_bot:
            return False
        variants = config["variants"]
        tc = config["time_controls"]
        inc_max = config.get("max_increment", 180)
        inc_min = config.get("min_increment", 0)
        modes = config["modes"]
        return self.is_supported_time_control(tc, inc_max, inc_min) and self.is_supported_variant(variants) and self.is_supported_mode(modes)

    def score(self):
        rated_bonus = Challenge.SCORE_BOOST if self.rated else 0
        titled_bonus = Challenge.SCORE_BOOST if self.challenger_master_title else 0

        return self.challenger_rating_int + rated_bonus + titled_bonus

    def mode(self):
        return Challenge.RATED if self.rated else Challenge.CASUAL

    def challenger_full_name(self):
        return "{}{}".format(
            self.challenger_title + " " if self.challenger_title else "",
            self.challenger_name
        )

    def __str__(self):
        return "{} {} challenge from {}({})".format(
            self.perf_name,
            self.mode(),
            self.challenger_full_name(),
            self.challenger_rating
        )

    def __repr__(self):
        return self.__str__()
