class Challenge():
    def __init__(self, c_info):
        self.id = c_info.get("id")
        self.rated = c_info.get("rated")
        self.variant = c_info.get("variant")["key"]
        self.perf_name = c_info.get("perf")["name"]
        self.speed = c_info.get("speed")
        self.challenger = c_info.get("challenger")["name"] if c_info.get("challenger") else "Anonymous"

    def is_supported_variant(self, supported):
        return self.variant in supported

    def is_supported_speed(self, supported):
        return self.speed in supported

    def is_supported_mode(self, supported):
        return "rated" in supported if self.rated else "casual" in supported

    def is_supported(self, config):
        variants = config["supported_variants"]
        tc = config["supported_tc"]
        modes = config["supported_modes"]
        return self.is_supported_speed(tc) and self.is_supported_variant(variants) and self.is_supported_mode(modes)

    def show(self):
        return "{} challenge from {}".format(self.perf_name, self.challenger)

class Game():
    def __init__(self, json, username, base_url):
        self.username = username
        self.id = json.get("id")
        self.speed = json.get("speed")
        self.clock_initial = json.get("clock")["initial"]
        self.clock_increment = json.get("clock")["increment"]
        self.perf_name = json.get("perf").get("name")
        self.variant_name = json.get("variant")["name"]
        self.white = Player(json.get("white"))
        self.black = Player(json.get("black"))
        self.initial_fen = json.get("initialFen")
        self.state = json.get("state")
        self.is_white = bool(self.white.name and self.white.name == username)
        self.my_color = "white" if self.is_white else "black"
        self.opponent_color = "black" if self.is_white else "white"
        self.me = self.white if self.is_white else self.black
        self.opponent = self.black if self.is_white else self.white
        self.base_url = base_url

    def url(self):
        return "{}/{}/{}".format(self.base_url, self.id, self.my_color)

    def show(self):
        return "{} {} vs {}".format(self.url(), self.perf_name, self.opponent.show())


class Player():
    def __init__(self, json):
        self.id = json.get("id")
        self.name = json.get("name")
        self.title = json.get("title")
        self.rating = json.get("rating")
        self.provisional = json.get("provisional")
        self.aiLevel = json.get("aiLevel")

    def show(self):
        if self.aiLevel:
            return "AI level {}".format(self.aiLevel)
        else:
            rating = "{}{}".format(self.rating, "?" if self.provisional else "")
            return "{}{}({})".format(self.title + " " if self.title else "", self.name, rating)
