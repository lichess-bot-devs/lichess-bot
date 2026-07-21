"""Test functions for the acceptance profile module."""
import math

from lib.acceptance_profile import acceptance_profile, finite_or_none
from lib.config import Configuration


def full_challenge_config() -> Configuration:
    """Create a configuration with an explicit challenge section."""
    return Configuration({
        "challenge": {
            "concurrency": 2,
            "accept_bot": True,
            "only_bot": False,
            "max_increment": 20,
            "min_increment": 0,
            "max_base": 1800,
            "min_base": 60,
            "max_days": math.inf,
            "min_days": 1,
            "variants": ["standard", "chess960"],
            "time_controls": ["bullet", "blitz"],
            "modes": ["casual", "rated"],
            "min_rating": 0,
            "max_rating": 4000,
            "block_list": [],
            "online_block_list": [],
            "allow_list": []
        }
    })


def test_finite_or_none() -> None:
    """Infinite and missing values become None; finite values pass through."""
    assert finite_or_none(math.inf) is None
    assert finite_or_none(None) is None
    assert finite_or_none(14) == 14
    assert finite_or_none(0) == 0


def test_acceptance_profile_shape() -> None:
    """The profile reflects the challenge config and is JSON serializable."""
    import json

    profile = acceptance_profile(full_challenge_config())
    assert profile["variants"] == ["standard", "chess960"]
    assert profile["timeControls"] == ["bullet", "blitz"]
    assert profile["modes"] == ["casual", "rated"]
    assert profile["clock"] == {"initialMin": 60, "initialMax": 1800, "incrementMin": 0, "incrementMax": 20}
    assert profile["days"] == {"min": 1, "max": None}
    assert profile["ratingRange"] == {"min": 0, "max": 4000}
    assert profile["acceptBot"] is True
    assert profile["onlyBot"] is False
    assert profile["concurrency"] == 2
    assert profile["hasAllowList"] is False
    assert profile["hasBlockList"] is False
    json.dumps(profile)  # Must not raise.


def test_acceptance_profile_lists() -> None:
    """Allow and block lists are exposed only as booleans, not contents."""
    config = full_challenge_config()
    config.config["challenge"]["allow_list"] = ["friendbot"]
    config.config["challenge"]["online_block_list"] = ["example.com/blocklist"]
    profile = acceptance_profile(config)
    assert profile["hasAllowList"] is True
    assert profile["hasBlockList"] is True
    assert "friendbot" not in str(profile)
