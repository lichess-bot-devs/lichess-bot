"""Proxy to access extra_game_handler functions, with default implementation if the file is missing."""
from lib import model
from typing import Any


def game_specific_options(game: model.Game) -> dict[str, Any]:
    """
    Return a dictionary of engine options based on game aspects.

    By default, if no custom extra_game_handler is found, an empty dict is returned so that the options
    in the configuration file are used.
    """
    try:
        from extra_game_handlers import game_specific_options
        return game_specific_options(game)
    except ImportError:
        pass

    return {}


def is_supported_extra(challenge: model.Challenge) -> bool:
    """
    Determine whether to accept a challenge.

    By default, if no custom extra_game_handler is found, True is returned so that there are no extra restrictions
    beyond those in the config file.
    """
    try:
        from extra_game_handlers import is_supported_extra
        return is_supported_extra(challenge)
    except ImportError:
        pass

    return True
