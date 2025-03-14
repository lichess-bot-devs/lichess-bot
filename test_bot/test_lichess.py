"""Tests for the lichess communication."""

from lib import lichess
import logging
import os
import pytest


def test_lichess() -> None:
    """Test the lichess communication."""
    token = os.environ.get("LICHESS_BOT_TEST_TOKEN")
    if not token:
        pytest.skip("Lichess-bot test token must be set.")
    li = lichess.Lichess(token, "https://lichess.org/", "0.0.0", logging.DEBUG, 3)
    assert len(li.get_online_bots()) > 20
    profile = li.get_profile()
    profile["seenAt"] = 1700000000000
    assert profile == {"blocking": False,
                       "count": {"ai": 3, "all": 12, "bookmark": 0, "draw": 1, "drawH": 1, "import": 0,
                                 "loss": 8, "lossH": 5, "me": 0, "playing": 0, "rated": 0, "win": 3, "winH": 3},
                       "createdAt": 1627834995597, "followable": True, "following": False, "id": "badsunfish",
                       "perfs": {"blitz": {"games": 0, "prog": 0, "prov": True, "rating": 1500, "rd": 500},
                                 "bullet": {"games": 0, "prog": 0, "prov": True, "rating": 1500, "rd": 500},
                                 "classical": {"games": 0, "prog": 0, "prov": True, "rating": 1500, "rd": 500},
                                 "correspondence": {"games": 0, "prog": 0, "prov": True, "rating": 1500, "rd": 500},
                                 "rapid": {"games": 0, "prog": 0, "prov": True, "rating": 1500, "rd": 500}},
                       "playTime": {"total": 1873, "tv": 0}, "seenAt": 1700000000000, "title": "BOT",
                       "url": "https://lichess.org/@/BadSunfish", "username": "BadSunfish"}
    assert li.get_ongoing_games() == []
    assert li.is_online("NNWithSF") is False
    public_data = li.get_public_data("lichapibot")
    for key in public_data["perfs"]:
        public_data["perfs"][key]["rd"] = 0
    assert public_data == {"blocking": False, "count": {"ai": 1, "all": 15774, "bookmark": 0, "draw": 3009, "drawH": 3009,
                                                        "import": 0, "loss": 6423, "lossH": 6423,
                                                        "me": 0, "playing": 0, "rated": 15121, "win": 6342, "winH": 6341},
                           "createdAt": 1524037267522, "followable": True, "following": False, "id": "lichapibot",
                           "perfs": {"blitz": {"games": 2430, "prog": 3, "prov": True, "rating": 2388, "rd": 0},
                                     "bullet": {"games": 7293, "prog": 9, "prov": True, "rating": 2298, "rd": 0},
                                     "classical": {"games": 0, "prog": 0, "prov": True, "rating": 1500, "rd": 0},
                                     "correspondence": {"games": 0, "prog": 0, "prov": True, "rating": 1500, "rd": 0},
                                     "rapid": {"games": 993, "prog": -80, "prov": True, "rating": 2363, "rd": 0}},
                           "playTime": {"total": 4111502, "tv": 1582068}, "profile": {},
                           "seenAt": 1669272254317, "title": "BOT", "tosViolation": True,
                           "url": "https://lichess.org/@/lichapibot", "username": "lichapibot"}
