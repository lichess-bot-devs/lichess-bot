"""Tests for the lichess communication."""

from lib import lichess
from lib.timer import Timer, seconds
from collections import defaultdict
from requests.models import Response
import logging
import os
import pytest
from typing import cast
from unittest.mock import patch
from lib.lichess_types import GameType
from lib.lichess import RateLimitedError

def mock_response(status_code: int, body: dict[str, object], headers: dict[str, str] | None = None) -> Response:
    """Create a mock HTTP response."""
    class MockResponse:
        def __init__(self) -> None:
            self.status_code = status_code
            self.headers = headers or {}

        def json(self) -> dict[str, object]:
            return dict(body)

    return cast(Response, MockResponse())


def lichess_without_init() -> lichess.Lichess:
    """Create a minimal Lichess instance without checking a real token."""
    li = object.__new__(lichess.Lichess)
    li.rate_limit_timers = defaultdict(Timer)
    li.challenge_rate_limit_backoff = seconds(60)
    return li


def test_challenge_429_without_ratelimit_body_sets_bot_rate_limit() -> None:
    """Generic challenge 429s should still block new challenge attempts."""
    li = lichess_without_init()
    response = mock_response(429, {"error": "Too many requests. Try again later."}, {"Retry-After": "120"})

    challenge_response = li.handle_challenge(response)

    assert challenge_response["bot_is_rate_limited"] is True
    assert challenge_response["opponent_is_rate_limited"] is False
    assert challenge_response["rate_limit_timeout"] == seconds(120)
    assert li.is_rate_limited(lichess.ENDPOINTS["challenge"])


def test_challenge_429_without_retry_after_uses_exponential_backoff() -> None:
    """Repeated generic challenge 429s should increase the local cooldown."""
    li = lichess_without_init()
    response = mock_response(429, {"error": "Too many requests. Try again later."})

    first_response = li.handle_challenge(response)
    second_response = li.handle_challenge(response)

    assert first_response["rate_limit_timeout"] == seconds(60)
    assert second_response["rate_limit_timeout"] == seconds(120)
    assert li.challenge_rate_limit_backoff == seconds(240)


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
                       "count": {"all": 12, "bookmark": 0, "draw": 1, "import": 0,
                                 "loss": 8, "me": 0, "playing": 0, "rated": 0, "win": 3},
                       "createdAt": 1627834995597, "followable": True, "following": False, "id": "badsunfish",
                       "perfs": {"blitz": {"games": 0, "prog": 0, "prov": True, "rating": 1500, "rd": 500},
                                 "bullet": {"games": 0, "prog": 0, "prov": True, "rating": 1500, "rd": 500},
                                 "classical": {"games": 0, "prog": 0, "prov": True, "rating": 1500, "rd": 500},
                                 "correspondence": {"games": 0, "prog": 0, "prov": True, "rating": 1500, "rd": 500},
                                 "rapid": {"games": 0, "prog": 0, "prov": True, "rating": 1500, "rd": 500}},
                       "playTime": {"human": 1595, "total": 1873, "tv": 0}, "seenAt": 1700000000000, "title": "BOT",
                       "url": "https://lichess.org/@/BadSunfish", "username": "BadSunfish"}
    assert li.get_ongoing_games() == []
    assert li.is_online("NNWithSF") is False
    public_data = li.get_public_data("lichapibot")
    for key in public_data["perfs"]:
        public_data["perfs"][key]["rd"] = 0
    assert public_data == {"blocking": False, "count": {"all": 15774, "bookmark": 0, "draw": 3009,
                                                        "import": 0, "loss": 6423,
                                                        "me": 0, "playing": 0, "rated": 15121, "win": 6342},
                           "createdAt": 1524037267522, "followable": True, "following": False, "id": "lichapibot",
                           "perfs": {"blitz": {"games": 2430, "prog": 3, "prov": True, "rating": 2388, "rd": 0},
                                     "bullet": {"games": 7293, "prog": 9, "prov": True, "rating": 2298, "rd": 0},
                                     "classical": {"games": 0, "prog": 0, "prov": True, "rating": 1500, "rd": 0},
                                     "correspondence": {"games": 0, "prog": 0, "prov": True, "rating": 1500, "rd": 0},
                                     "rapid": {"games": 993, "prog": -80, "prov": True, "rating": 2363, "rd": 0}},
                           "playTime": {"total": 4111502, "tv": 1582068, "human": 534785}, "profile": {},
                           "seenAt": 1669272254317, "title": "BOT", "tosViolation": True,
                           "url": "https://lichess.org/@/lichapibot", "username": "lichapibot"}


@pytest.mark.parametrize(("endpoint_name","url"), [("profile","/api/account"), ("playing","/api/account/playing"),
                                 ("stream","/api/bot/game/stream/{}"),("stream_event","/api/stream/event"),
                                 ("move","/api/bot/game/{}/move/{}"),("takeback","/api/bot/game/{}/takeback/{}"),
                                 ("chat","/api/bot/game/{}/chat"),
                                 ("abort","/api/bot/game/{}/abort"),("accept","/api/challenge/{}/accept"),
                                 ("decline","/api/challenge/{}/decline"),
                                 ("upgrade","/api/bot/account/upgrade"),("resign","/api/bot/game/{}/resign"),
                                 ("export","/game/export/{}"),("online_bots","/api/bot/online"),
                                 ("challenge","/api/challenge/{}"),("cancel","/api/challenge/{}/cancel"),
                                 ("status","/api/users/status"),("public_data","/api/user/{}"),("token_test","/api/token/test")])
def test_rate_limited_path_template(endpoint_name: str,url: str) -> None:
    """An exception will be thrown if the path template is rate limited."""
    li = lichess_without_init()
    with (patch.object(li,"is_rate_limited",return_value=True) as is_rate_limi,
        pytest.raises(RateLimitedError, match=f"{url} is rate-limited")
    ):
        li.get_path_template(endpoint_name)
    is_rate_limi.assert_called_once_with(url)


def test_get_game_pgn_returns_empty_string_on_error() -> None:
    """An API error while getting PGN record of a game return an empty string."""
    li = lichess_without_init()
    game: GameType = {"gameId": "game-id"}
    with patch.object(li, "api_get_raw", side_effect=RuntimeError):
        assert li.get_game_pgn(game["gameId"]) == ""
