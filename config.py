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
                    ["supported_tc", list, "Section `supported_tc` must be a list with indented entries starting with dashes.."],
                    ["supported_modes", list, "Section `supported_modes` must be a list with indented entries starting with dashes.."]]
        for section in sections:
            if section[0] not in CONFIG:
                raise Exception("Your config.yml does not have required section `{}`.".format(section[0]))
            elif not isinstance(CONFIG[section[0]], section[1]):
                raise Exception(section[2])


        engine_sections = [["dir", str, "´dir´ must be a string wrapped in quotes."],
                           ["name", str, "´name´ must be a string wrapped in quotes."],
                           ["polyglot", bool, "´polyglot´ must be a boolean type: true or false."],
                           ["polyglot_book", str, "´polyglot_book´ must be a string wrapped in quotes."],
                           ["polyglot_max_depth", int, "`polyglot_max_depth` must be an integer number without quotes."],
                           ["polyglot_min_weight", int, "`polyglot_min_weight` must be an integer number without quotes."],
                           ["polyglot_random", bool, "`polyglot_random` must be a boolean type: true or false."]]

        for subsection in engine_sections:
            if subsection[0] not in CONFIG["engine"]:
                raise Exception("Your config.yml does not have required `engine` subsection `{}`.".format(subsection))
            if not isinstance(CONFIG["engine"][subsection[0]], subsection[1]):
                raise Exception("´engine´ subsection {}".format(subsection[2]))

        if CONFIG["token"] == "xxxxxxxxxxxxxxxx":
            raise Exception("Your config.yml has the default Lichess API token. This is probably wrong.")

        if not os.path.isdir(CONFIG["engine"]["dir"]):
            raise Exception("Your engine directory `{}` is not a directory.")

        engine = os.path.join(CONFIG["engine"]["dir"], CONFIG["engine"]["name"])

        if not os.path.isfile(engine):
            raise Exception("The engine %s file does not exist." % engine)

        if not os.access(engine, os.X_OK):
            raise Exception("The engine %s doesn't have execute (x) permission. Try: chmod +x %s" % (engine, engine))

        if (CONFIG["engine"]["polyglot"] == True):
            book_dir = os.path.join(CONFIG["engine"]["dir"], CONFIG["engine"]["polyglot_book"])
            if not os.path.isfile(book_dir):
                raise Exception("The polyglot book %s file does not exist." % book_dir)
            CONFIG["engine"]["polyglot_book"] = book_dir

    return CONFIG
