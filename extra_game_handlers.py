"""Functions for the user to implement when the config file is not adequate to express bot requirements."""
from lib import model
from lib.lichess_types import OPTIONS_TYPE


def game_specific_options(game: model.Game) -> OPTIONS_TYPE:  # noqa: ARG001
    """
    Return a dictionary of engine options based on game aspects.

    By default, an empty dict is returned so that the options in the configuration file are used.
    """
    return {}


def is_supported_extra(challenge: model.Challenge) -> bool:  # noqa: ARG001
    """
    Determine whether to accept a challenge.

    By default, True is always returned so that there are no extra restrictions beyond those in the config file.
    """
    return True
