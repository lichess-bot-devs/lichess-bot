import yaml
import os
import os.path

def load_config():
    with open("./config.yml", 'r') as stream:
        try:
            CONFIG = yaml.load(stream)
        except Exception as e:
            print("There appears to be a syntax problem with your config.yml")
            raise e

        #[section, type, error message]
        sections = [["token", str, "Section `token` must be a string wrapped in quotes."],
                    ["url", str, "Section `url` must be a string wrapped in quotes."],
                    ["engine", dict, "Section `engine` must be a dictionary with indented keys followed by colons.."],
                    ["max_concurrent_games", int, "Section `max_concurrent_games` must be an integer number without quotes."],
                    ["max_queued_challenges", int, "Section `max_queued_challenges` must be an integer number without quotes."],
                    ["supported_tc", list, "Section `supported_tc` must be a list with indented entries starting with dashes.."],
                    ["supported_modes", list, "Section `supported_modes` must be a list with indented entries starting with dashes.."]]
        for section in sections:
            if section[0] not in CONFIG:
                raise Exception("Your config.yml does not have required section `{}`.".format(section[0]))
            elif not isinstance(CONFIG[section[0]], section[1]):
                raise Exception(section[2])


        engine_sections = ["dir", "name"]
        for subsection in engine_sections:
            if subsection not in CONFIG["engine"]:
                raise Exception("Your config.yml does not have required `engine` subsection `{}`.".format(subsection))
            if not isinstance(CONFIG["engine"][subsection], str):
                raise Exception("Engine subsection `{}` must be a string wrapped in quotes.".format(subsection))

        if CONFIG["token"] == "xxxxxxxxxxxxxxxx":
            raise Exception("Your config.yml has the default Lichess API token. This is probably wrong.")

        if not os.path.isdir(CONFIG["engine"]["dir"]):
            raise Exception("Your engine directory `{}` is not a directory.")

        if not os.path.exists(CONFIG["engine"]["dir"] + CONFIG["engine"]["name"]):
            raise Exception("The engine specified does not exist.")
    return CONFIG
