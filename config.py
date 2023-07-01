"""Code related to the config that lichess-bot uses."""
import yaml
import os
import os.path
import logging
import math
from abc import ABCMeta
from enum import Enum
from typing import Any
CONFIG_DICT_TYPE = dict[str, Any]

logger = logging.getLogger(__name__)


class FilterType(str, Enum):
    """What to do if the opponent declines our challenge."""

    NONE = "none"
    """Will still challenge the opponent."""
    COARSE = "coarse"
    """Won't challenge the opponent again."""
    FINE = "fine"
    """
    Won't challenge the opponent to a game of the same mode, speed, and variant
    based on the reason for the opponent declining the challenge.
    """


class Configuration:
    """The config or a sub-config that the bot uses."""

    def __init__(self, parameters: CONFIG_DICT_TYPE) -> None:
        """:param parameters: A `dict` containing the config for the bot."""
        self.config = parameters

    def __getattr__(self, name: str) -> Any:
        """
        Enable the use of `config.key1.key2`.

        :param name: The key to get its value.
        :return: The value of the key.
        """
        return self.lookup(name)

    def lookup(self, name: str) -> Any:
        """
        Get the value of a key.

        :param name: The key to get its value.
        :return: `Configuration` if the value is a `dict` else returns the value.
        """
        data = self.config.get(name)
        return Configuration(data) if isinstance(data, dict) else data

    def items(self) -> Any:
        """:return: All the key-value pairs in this config."""
        return self.config.items()

    def __bool__(self) -> bool:
        """Whether `self.config` is empty."""
        return bool(self.config)

    def __getstate__(self) -> CONFIG_DICT_TYPE:
        """Get `self.config`."""
        return self.config

    def __setstate__(self, d: CONFIG_DICT_TYPE) -> None:
        """Set `self.config`."""
        self.config = d


def config_assert(assertion: bool, error_message: str) -> None:
    """Raise an exception if an assertion is false."""
    if not assertion:
        raise Exception(error_message)


def check_config_section(config: CONFIG_DICT_TYPE, data_name: str, data_type: ABCMeta, subsection: str = "") -> None:
    """
    Check the validity of a config section.

    :param config: The config section.
    :param data_name: The key to check its value.
    :param data_type: The expected data type.
    :param subsection: The subsection of the key.
    """
    config_part = config[subsection] if subsection else config
    sub = f"`{subsection}` sub" if subsection else ""
    data_location = f"`{data_name}` subsection in `{subsection}`" if subsection else f"Section `{data_name}`"
    type_error_message = {str: f"{data_location} must be a string wrapped in quotes.",
                          dict: f"{data_location} must be a dictionary with indented keys followed by colons."}
    config_assert(data_name in config_part, f"Your config.yml does not have required {sub}section `{data_name}`.")
    config_assert(isinstance(config_part[data_name], data_type), type_error_message[data_type])


def set_config_default(config: CONFIG_DICT_TYPE, *sections: str, key: str, default: Any,
                       force_empty_values: bool = False) -> CONFIG_DICT_TYPE:
    """
    Fill a specific config key with the default value if it is missing.

    :param config: The bot's config.
    :param sections: The sections that the key is in.
    :param key: The key to set.
    :param default: The default value.
    :param force_empty_values: Whether an empty value should be replaced with the default value.
    :return: The new config with the default value inserted if needed.
    """
    subconfig = config
    for section in sections:
        subconfig = subconfig.setdefault(section, {})
        if not isinstance(subconfig, dict):
            raise Exception(f'The {section} section in {sections} should hold a set of key-value pairs, not a value.')
    if force_empty_values:
        if subconfig.get(key) in [None, ""]:
            subconfig[key] = default
    else:
        subconfig.setdefault(key, default)
    return subconfig


def change_value_to_list(config: CONFIG_DICT_TYPE, *sections: str, key: str) -> None:
    """
    Change a single value to a list. e.g. 60 becomes [60]. Used to maintain backwards compatibility.

    :param config: The bot's config.
    :param sections: The sections that the key is in.
    :param key: The key to set.
    """
    subconfig = set_config_default(config, *sections, key=key, default=[])

    if subconfig[key] is None:
        subconfig[key] = []

    if not isinstance(subconfig[key], list):
        subconfig[key] = [subconfig[key]]


def insert_default_values(CONFIG: CONFIG_DICT_TYPE) -> None:
    """
    Insert the default values of most keys to the config if they are missing.

    :param CONFIG: The bot's config.
    """
    set_config_default(CONFIG, key="abort_time", default=20)
    set_config_default(CONFIG, key="move_overhead", default=1000)
    set_config_default(CONFIG, key="rate_limiting_delay", default=0)
    set_config_default(CONFIG, "engine", key="working_dir", default=os.getcwd(), force_empty_values=True)
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
    set_config_default(CONFIG, "engine", "online_moves", key="max_retries", default=2, force_empty_values=True)
    set_config_default(CONFIG, "engine", "online_moves", "online_egtb", key="enabled", default=False)
    set_config_default(CONFIG, "engine", "online_moves", "online_egtb", key="source", default="lichess")
    set_config_default(CONFIG, "engine", "online_moves", "online_egtb", key="min_time", default=20)
    set_config_default(CONFIG, "engine", "online_moves", "online_egtb", key="max_pieces", default=7)
    set_config_default(CONFIG, "engine", "online_moves", "online_egtb", key="move_quality", default="best")
    set_config_default(CONFIG, "engine", "online_moves", "chessdb_book", key="enabled", default=False)
    set_config_default(CONFIG, "engine", "online_moves", "chessdb_book", key="min_time", default=20)
    set_config_default(CONFIG, "engine", "online_moves", "chessdb_book", key="move_quality", default="good")
    set_config_default(CONFIG, "engine", "online_moves", "chessdb_book", key="min_depth", default=20)
    set_config_default(CONFIG, "engine", "online_moves", "lichess_cloud_analysis", key="enabled", default=False)
    set_config_default(CONFIG, "engine", "online_moves", "lichess_cloud_analysis", key="min_time", default=20)
    set_config_default(CONFIG, "engine", "online_moves", "lichess_cloud_analysis", key="move_quality", default="best")
    set_config_default(CONFIG, "engine", "online_moves", "lichess_cloud_analysis", key="min_depth", default=20)
    set_config_default(CONFIG, "engine", "online_moves", "lichess_cloud_analysis", key="min_knodes", default=0)
    set_config_default(CONFIG, "engine", "online_moves", "lichess_cloud_analysis", key="max_score_difference", default=50)
    set_config_default(CONFIG, "engine", "online_moves", "lichess_opening_explorer", key="enabled", default=False)
    set_config_default(CONFIG, "engine", "online_moves", "lichess_opening_explorer", key="min_time", default=20)
    set_config_default(CONFIG, "engine", "online_moves", "lichess_opening_explorer", key="source", default="masters")
    set_config_default(CONFIG, "engine", "online_moves", "lichess_opening_explorer", key="player_name", default="")
    set_config_default(CONFIG, "engine", "online_moves", "lichess_opening_explorer", key="sort", default="winrate")
    set_config_default(CONFIG, "engine", "online_moves", "lichess_opening_explorer", key="min_games", default=10)
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
    set_config_default(CONFIG, "challenge", key="block_list", default=[], force_empty_values=True)
    set_config_default(CONFIG, "correspondence", key="checkin_period", default=600)
    set_config_default(CONFIG, "correspondence", key="move_time", default=60, force_empty_values=True)
    set_config_default(CONFIG, "correspondence", key="disconnect_time", default=300)
    set_config_default(CONFIG, "matchmaking", key="challenge_timeout", default=30, force_empty_values=True)
    CONFIG["matchmaking"]["challenge_timeout"] = max(CONFIG["matchmaking"]["challenge_timeout"], 1)
    set_config_default(CONFIG, "matchmaking", key="block_list", default=[], force_empty_values=True)
    default_filter = (CONFIG.get("matchmaking") or {}).get("delay_after_decline") or FilterType.NONE.value
    set_config_default(CONFIG, "matchmaking", key="challenge_filter", default=default_filter, force_empty_values=True)
    set_config_default(CONFIG, "matchmaking", key="allow_matchmaking", default=False)
    set_config_default(CONFIG, "matchmaking", key="challenge_initial_time", default=[None], force_empty_values=True)
    change_value_to_list(CONFIG, "matchmaking", key="challenge_initial_time")
    set_config_default(CONFIG, "matchmaking", key="challenge_increment", default=[None], force_empty_values=True)
    change_value_to_list(CONFIG, "matchmaking", key="challenge_increment")
    set_config_default(CONFIG, "matchmaking", key="challenge_days", default=[None], force_empty_values=True)
    change_value_to_list(CONFIG, "matchmaking", key="challenge_days")
    set_config_default(CONFIG, "matchmaking", key="opponent_min_rating", default=600, force_empty_values=True)
    set_config_default(CONFIG, "matchmaking", key="opponent_max_rating", default=4000, force_empty_values=True)
    set_config_default(CONFIG, "matchmaking", key="opponent_allow_tos_violation", default=True)
    set_config_default(CONFIG, "matchmaking", key="challenge_variant", default="random")
    set_config_default(CONFIG, "matchmaking", key="challenge_mode", default="random")

    for section in ["engine", "correspondence"]:
        for ponder in ["ponder", "uci_ponder"]:
            set_config_default(CONFIG, section, key=ponder, default=False)

    for type in ["hello", "goodbye"]:
        for target in ["", "_spectators"]:
            set_config_default(CONFIG, "greeting", key=type + target, default="", force_empty_values=True)


def log_config(CONFIG: CONFIG_DICT_TYPE) -> None:
    """
    Log the config to make debugging easier.

    :param CONFIG: The bot's config.
    """
    logger_config = CONFIG.copy()
    logger_config["token"] = "logger"
    logger.debug(f"Config:\n{yaml.dump(logger_config, sort_keys=False)}")
    logger.debug("====================")


def validate_config(CONFIG: CONFIG_DICT_TYPE) -> None:
    """Check if the config is valid."""
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

    matchmaking = CONFIG.get("matchmaking") or {}
    matchmaking_enabled = matchmaking.get("allow_matchmaking") or False
    # `, []` is there only for mypy. It isn't used.
    matchmaking_has_values = (matchmaking.get("challenge_initial_time", [])[0] is not None
                              and matchmaking.get("challenge_increment", [])[0] is not None
                              or matchmaking.get("challenge_days", [])[0] is not None)
    config_assert(not matchmaking_enabled or matchmaking_has_values,
                  "The time control to challenge other bots is not set. Either lists of challenge_initial_time and "
                  "challenge_increment is required, or a list of challenge_days, or both.")

    filter_option = "challenge_filter"
    filter_type = (CONFIG.get("matchmaking") or {}).get(filter_option)
    config_assert(filter_type is None or filter_type in FilterType.__members__.values(),
                  f"{filter_type} is not a valid value for {filter_option} (formerly delay_after_decline) parameter. "
                  f"Choices are: {', '.join(FilterType)}.")

    selection_choices = {"polyglot":               ["weighted_random", "uniform_random", "best_move"],
                         "chessdb_book":           ["all", "good", "best"],
                         "lichess_cloud_analysis": ["good", "best"],
                         "online_egtb":            ["good", "best", "suggest"]}
    for db_name, valid_selections in selection_choices.items():
        is_online = db_name != "polyglot"
        db_section = (CONFIG["engine"].get("online_moves") or {}) if is_online else CONFIG["engine"]
        db_config = db_section.get(db_name)
        select_key = "selection" if db_name == "polyglot" else "move_quality"
        selection = db_config.get(select_key)
        select = f"{'online_moves:' if is_online else ''}{db_name}:{select_key}"
        config_assert(selection in valid_selections,
                        f"'{selection}' is not a valid 'engine:{select}' value. "
                        f"Please choose from {valid_selections}.")

    lichess_tbs_config = CONFIG["engine"].get("lichess_bot_tbs") or {}
    quality_selections = ["good", "best", "suggest"]
    for tb in ["syzygy", "gaviota"]:
        selection = lichess_tbs_config.get(tb).get("move_quality")
        config_assert(selection in quality_selections,
                      f"`{selection}` is not a valid choice for `engine:lichess_bot_tbs:{tb}:move_quality. "
                      f"Please choose from {quality_selections}.")


    explorer_choices = {"source": ["lichess", "masters", "player"],
                        "sort": ["winrate", "games_played"]}
    explorer_config = (CONFIG["engine"].get("online_moves") or {}).get("lichess_opening_explorer")
    if explorer_config:
        for parameter, choice_list in explorer_choices.items():
            explorer_choice = explorer_config.get(parameter)
            config_assert(explorer_choice in choice_list,
                            f"`{explorer_choice}` is not a valid"
                            f" `engine:online_moves:lichess_opening_explorer:{parameter}`"
                            f" value. Please choose from {choice_list}.")


def load_config(config_file: str) -> Configuration:
    """
    Read the config.

    :param config_file: The filename of the config (usually `config.yml`).
    :return: A `Configuration` object containing the config.
    """
    with open(config_file) as stream:
        try:
            CONFIG = yaml.safe_load(stream)
        except Exception:
            logger.exception("There appears to be a syntax problem with your config.yml")
            raise

    log_config(CONFIG)

    if "LICHESS_BOT_TOKEN" in os.environ:
        CONFIG["token"] = os.environ["LICHESS_BOT_TOKEN"]

    insert_default_values(CONFIG)
    log_config(CONFIG)
    validate_config(CONFIG)

    return Configuration(CONFIG)
