import yaml
import os
import os.path
import logging

logger = logging.getLogger(__name__)


def config_assert(assertion, error_message):
    if not assertion:
        raise Exception(error_message)


def check_config_section(config, data_name, data_type, subsection=""):
    config_part = config[subsection] if subsection else config
    sub = f"`{subsection}` sub" if subsection else ""
    data_location = f"`{data_name}` subsection in `{subsection}`" if subsection else f"Section `{data_name}`"
    type_error_message = {str:  f"{data_location} must be a string wrapped in quotes.",
                          dict: f"{data_location} must be a dictionary with indented keys followed by colons."}
    config_assert(data_name in config_part, f"Your config.yml does not have required {sub}section `{data_name}`.")
    config_assert(isinstance(config_part[data_name], data_type), type_error_message[data_type])


def load_config(config_file):
    with open(config_file) as stream:
        try:
            CONFIG = yaml.safe_load(stream)
        except Exception:
            logger.exception("There appears to be a syntax problem with your config.yml")
            raise

        logger_config = CONFIG.copy()
        logger_config["token"] = "logger"
        logger.debug(f"Config:\n{yaml.dump(logger_config, sort_keys=False)}")

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

    return CONFIG
