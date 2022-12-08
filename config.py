import yaml
import os
import os.path
import logging
import math
from matchmaking import DelayType

logger = logging.getLogger(__name__)


class Configuration:
    def __init__(self, parameters):
        self.config = parameters

    def __getattr__(self, name):
        return self.lookup(name)

    def lookup(self, name):
        data = self.config.get(name)
        return Configuration(data) if isinstance(data, dict) else data

    def items(self):
        return self.config.items()

    def __bool__(self):
        return bool(self.config)

    def __getstate__(self):
        return self.config

    def __setstate__(self, d):
        self.config = d


def config_assert(assertion, error_message):
    if not assertion:
        raise Exception(error_message)


def check_config_section(config, data_name, data_type, subsection=""):
    config_part = config[subsection] if subsection else config
    sub = f"`{subsection}` sub" if subsection else ""
    data_location = f"`{data_name}` subsection in `{subsection}`" if subsection else f"Section `{data_name}`"
    type_error_message = {str: f"{data_location} must be a string wrapped in quotes.",
                          dict: f"{data_location} must be a dictionary with indented keys followed by colons."}
    config_assert(data_name in config_part, f"Your config.yml does not have required {sub}section `{data_name}`.")
    config_assert(isinstance(config_part[data_name], data_type), type_error_message[data_type])


def set_config_default(config, *sections, key, default, force_falsey_values=False):
    subconfig = config
    for section in sections:
        subconfig = subconfig.setdefault(section, {})
        if not isinstance(subconfig, dict):
            raise Exception(f'The {section} section in {sections} should hold a set of key-value pairs, not a value.')
    if force_falsey_values:
        subconfig[key] = subconfig.get(key) or default
    else:
        subconfig.setdefault(key, default)
    return subconfig


def change_value_to_list(config, *sections, key):
    subconfig = set_config_default(config, *sections, key=key, default=[])
    if not isinstance(subconfig[key], list):
        subconfig[key] = [subconfig[key]]


def insert_default_values(CONFIG):
    set_config_default(CONFIG, key="abort_time", default=20)
    set_config_default(CONFIG, key="move_overhead", default=1000)
    set_config_default(CONFIG, key="rate_limiting_delay", default=0)
    set_config_default(CONFIG, "engine", key="working_dir", default=os.getcwd(), force_falsey_values=True)
    set_config_default(CONFIG, "engine", key="silence_stderr", default=False)
    set_config_default(CONFIG, "engine", "draw_or_resign", key="offer_draw_enabled", default=False)
    set_config_default(CONFIG, "engine", "draw_or_resign", key="offer_draw_for_egtb_zero", default=True)
    set_config_default(CONFIG, "engine", "draw_or_resign", key="resign_enabled", default=False)
    set_config_default(CONFIG, "engine", "draw_or_resign", key="resign_for_egtb_minus_two", default=True)
    set_config_default(CONFIG, "engine", "draw_or_resign", key="resign_moves", default=3)
    set_config_default(CONFIG, "engine", "draw_or_resign", key="resign_score", default=-1000)
    set_config_default(CONFIG, "engine", "draw_or_resign", key="offer_draw_moves", default=5)
    set_config_default(CONFIG, "engine", "draw_or_resign", key="offer_draw_score", default=0)
    set_config_default(CONFIG, "engine", "draw_or_resign", key="offer_draw_pieces", default=10)
    set_config_default(CONFIG, "engine", "online_moves", key="max_out_of_book_moves", default=10)
    set_config_default(CONFIG, "engine", "online_moves", key="max_retries", default=2, force_falsey_values=True)
    set_config_default(CONFIG, "engine", "online_moves", "online_egtb", key="enabled", default=False)
    set_config_default(CONFIG, "engine", "online_moves", "online_egtb", key="source", default="lichess")
    set_config_default(CONFIG, "engine", "online_moves", "online_egtb", key="min_time", default=20)
    set_config_default(CONFIG, "engine", "online_moves", "online_egtb", key="max_pieces", default=7)
    set_config_default(CONFIG, "engine", "online_moves", "online_egtb", key="move_quality", default="best")
    set_config_default(CONFIG, "engine", "online_moves", "chessdb_book", key="enabled", default=False)
    set_config_default(CONFIG, "engine", "online_moves", "chessdb_book", key="min_time", default=20)
    set_config_default(CONFIG, "engine", "online_moves", "chessdb_book", key="move_quality", default="good")
    set_config_default(CONFIG, "engine", "online_moves", "chessdb_book", key="min_depth", default=20)
    set_config_default(CONFIG, "engine", "online_moves", "chessdb_book", key="contribute", default=True)
    set_config_default(CONFIG, "engine", "online_moves", "lichess_cloud_analysis", key="enabled", default=False)
    set_config_default(CONFIG, "engine", "online_moves", "lichess_cloud_analysis", key="min_time", default=20)
    set_config_default(CONFIG, "engine", "online_moves", "lichess_cloud_analysis", key="move_quality", default="best")
    set_config_default(CONFIG, "engine", "online_moves", "lichess_cloud_analysis", key="min_depth", default=20)
    set_config_default(CONFIG, "engine", "online_moves", "lichess_cloud_analysis", key="min_knodes", default=0)
    set_config_default(CONFIG, "engine", "online_moves", "lichess_cloud_analysis", key="max_score_difference", default=50)
    set_config_default(CONFIG, "engine", "lichess_bot_tbs", "syzygy", key="enabled", default=False)
    set_config_default(CONFIG, "engine", "lichess_bot_tbs", "syzygy", key="max_pieces", default=7)
    set_config_default(CONFIG, "engine", "lichess_bot_tbs", "syzygy", key="move_quality", default="best")
    set_config_default(CONFIG, "engine", "lichess_bot_tbs", "gaviota", key="enabled", default=False)
    set_config_default(CONFIG, "engine", "lichess_bot_tbs", "gaviota", key="max_pieces", default=5)
    set_config_default(CONFIG, "engine", "lichess_bot_tbs", "gaviota", key="move_quality", default="best")
    set_config_default(CONFIG, "engine", "lichess_bot_tbs", "gaviota", key="min_dtm_to_consider_as_wdl_1", default=120)
    set_config_default(CONFIG, "engine", "polyglot", key="enabled", default=False)
    set_config_default(CONFIG, "engine", "polyglot", key="max_depth", default=8)
    set_config_default(CONFIG, "engine", "polyglot", key="selection", default="weighted_random")
    set_config_default(CONFIG, "engine", "polyglot", key="min_weight", default=1)
    set_config_default(CONFIG, "challenge", key="concurrency", default=1)
    set_config_default(CONFIG, "challenge", key="sort_by", default="best")
    set_config_default(CONFIG, "challenge", key="accept_bot", default=False)
    set_config_default(CONFIG, "challenge", key="only_bot", default=False)
    set_config_default(CONFIG, "challenge", key="max_increment", default=180)
    set_config_default(CONFIG, "challenge", key="min_increment", default=0)
    set_config_default(CONFIG, "challenge", key="max_base", default=math.inf)
    set_config_default(CONFIG, "challenge", key="min_base", default=0)
    set_config_default(CONFIG, "challenge", key="max_days", default=math.inf)
    set_config_default(CONFIG, "challenge", key="min_days", default=1)
    set_config_default(CONFIG, "challenge", key="block_list", default=[])
    set_config_default(CONFIG, "correspondence", key="checkin_period", default=600)
    set_config_default(CONFIG, "correspondence", key="move_time", default=60, force_falsey_values=True)
    set_config_default(CONFIG, "correspondence", key="disconnect_time", default=300)
    set_config_default(CONFIG, "matchmaking", key="challenge_timeout", default=30, force_falsey_values=True)
    CONFIG["matchmaking"]["challenge_timeout"] = max(CONFIG["matchmaking"]["challenge_timeout"], 1)
    set_config_default(CONFIG, "matchmaking", key="block_list", default=[], force_falsey_values=True)
    set_config_default(CONFIG, "matchmaking", key="delay_after_decline", default=DelayType.NONE, force_falsey_values=True)
    set_config_default(CONFIG, "matchmaking", key="allow_matchmaking", default=False)
    set_config_default(CONFIG, "matchmaking", key="challenge_initial_time", default=[60])
    change_value_to_list(CONFIG, "matchmaking", key="challenge_initial_time")
    set_config_default(CONFIG, "matchmaking", key="challenge_increment", default=[2])
    change_value_to_list(CONFIG, "matchmaking", key="challenge_increment")
    set_config_default(CONFIG, "matchmaking", key="challenge_days", default=[None])
    change_value_to_list(CONFIG, "matchmaking", key="challenge_days")
    set_config_default(CONFIG, "matchmaking", key="opponent_min_rating", default=600, force_falsey_values=True)
    set_config_default(CONFIG, "matchmaking", key="opponent_max_rating", default=4000, force_falsey_values=True)
    set_config_default(CONFIG, "matchmaking", key="opponent_allow_tos_violation", default=True)
    set_config_default(CONFIG, "matchmaking", key="challenge_variant", default="random")
    set_config_default(CONFIG, "matchmaking", key="challenge_mode", default="random")

    for section in ["engine", "correspondence"]:
        for ponder in ["ponder", "uci_ponder"]:
            set_config_default(CONFIG, section, key=ponder, default=False)

    for type in ["hello", "goodbye"]:
        for target in ["", "_spectators"]:
            set_config_default(CONFIG, "greeting", key=type + target, default="", force_falsey_values=True)


def log_config(CONFIG):
    logger_config = CONFIG.copy()
    logger_config["token"] = "logger"
    logger.debug(f"Config:\n{yaml.dump(logger_config, sort_keys=False)}")
    logger.debug("====================")


def load_config(config_file):
    with open(config_file) as stream:
        try:
            CONFIG = yaml.safe_load(stream)
        except Exception:
            logger.exception("There appears to be a syntax problem with your config.yml")
            raise

        log_config(CONFIG)

        if "LICHESS_BOT_TOKEN" in os.environ:
            CONFIG["token"] = os.environ["LICHESS_BOT_TOKEN"]

        check_config_section(CONFIG, "token", str)
        check_config_section(CONFIG, "url", str)
        check_config_section(CONFIG, "engine", dict)
        check_config_section(CONFIG, "challenge", dict)
        check_config_section(CONFIG, "dir", str, "engine")
        check_config_section(CONFIG, "name", str, "engine")

        config_assert(CONFIG["token"] != "xxxxxxxxxxxxxxxx",
                      "Your config.yml has the default Lichess API token. This is probably wrong.")
        config_assert(os.path.isdir(CONFIG["engine"]["dir"]),
                      f'Your engine directory `{CONFIG["engine"]["dir"]}` is not a directory.')

        working_dir = CONFIG["engine"].get("working_dir")
        config_assert(not working_dir or os.path.isdir(working_dir),
                      f"Your engine's working directory `{working_dir}` is not a directory.")

        engine = os.path.join(CONFIG["engine"]["dir"], CONFIG["engine"]["name"])
        config_assert(os.path.isfile(engine) or CONFIG["engine"]["protocol"] == "homemade",
                      f"The engine {engine} file does not exist.")
        config_assert(os.access(engine, os.X_OK) or CONFIG["engine"]["protocol"] == "homemade",
                      f"The engine {engine} doesn't have execute (x) permission. Try: chmod +x {engine}")

        if CONFIG["engine"]["protocol"] == "xboard":
            for section, subsection in (("online_moves", "online_egtb"),
                                        ("lichess_bot_tbs", "syzygy"),
                                        ("lichess_bot_tbs", "gaviota")):
                online_section = (CONFIG["engine"].get(section) or {}).get(subsection) or {}
                config_assert(online_section.get("move_quality") != "suggest" or not online_section.get("enabled"),
                              f"XBoard engines can't be used with `move_quality` set to `suggest` in {subsection}.")

    insert_default_values(CONFIG)
    log_config(CONFIG)
    return Configuration(CONFIG)
