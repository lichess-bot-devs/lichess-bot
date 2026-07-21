"""Derive a machine-readable acceptance profile from the bot's challenge configuration.

The profile summarizes which challenges this bot will accept, as declared in the
`challenge:` section of the configuration file. It is logged at startup so bot
operators can see at a glance what their bot accepts, and it matches the payload
shape proposed for a future lichess `POST /api/bot/matchmaking/profile` endpoint
(see https://github.com/lichess-org/lila server-side matchmaking pools proposal).
"""
import math
from typing import Any

from lib.config import Configuration


def finite_or_none(value: float | int | None) -> float | int | None:
    """Convert infinite config values (e.g. `max_days: .inf`) to None for JSON serialization."""
    if value is None or (isinstance(value, float) and math.isinf(value)):
        return None
    return value


def acceptance_profile(config: Configuration) -> dict[str, Any]:
    """
    Build the acceptance profile from the `challenge:` section of the config.

    :param config: The bot's full configuration.
    :return: A JSON-serializable dictionary describing which challenges the bot accepts.
    """
    challenge = config.challenge
    return {"variants": list(challenge.variants or []),
            "timeControls": list(challenge.time_controls or []),
            "modes": list(challenge.modes or []),
            "clock": {"initialMin": challenge.min_base,
                      "initialMax": finite_or_none(challenge.max_base),
                      "incrementMin": challenge.min_increment,
                      "incrementMax": challenge.max_increment},
            "days": {"min": finite_or_none(challenge.min_days),
                     "max": finite_or_none(challenge.max_days)},
            "ratingRange": {"min": challenge.min_rating,
                            "max": challenge.max_rating},
            "acceptBot": bool(challenge.accept_bot),
            "onlyBot": bool(challenge.only_bot),
            "concurrency": challenge.concurrency,
            "hasAllowList": bool(challenge.allow_list),
            "hasBlockList": bool(challenge.block_list or challenge.online_block_list)}
