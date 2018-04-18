class Challenge():
    def __init__(self, c_info):
        self.id = c_info.get("id")
        self.rated = c_info.get("rated")
        self.variant = c_info.get("variant")["key"]
        self.perf = c_info.get("perf")["name"]
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
