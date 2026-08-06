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
from lib.lichess_types import GameType, PublicDataType, TOKEN_TESTS_TYPE, UserProfileType


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


def test_init_accepts_bot_play_scope() -> None:
    """A token with the bot:play scope should initialize the client."""
    test_value = "test-token"
    token_response: TOKEN_TESTS_TYPE = {test_value: {"scopes": "challenge:read,bot:play"}}

    with patch.object(lichess.Lichess, "api_post", return_value=token_response) as api_post:
        li = lichess.Lichess(test_value, "https://lichess.org/", "0.0.0", logging.DEBUG, 3)

    assert li.header["Authorization"] == f"Bearer {test_value}"
    api_post.assert_called_once_with("token_test", data=test_value)


def test_init_rejects_unknown_token() -> None:
    """Initialization should fail when the token test does not return the token."""
    with (
        patch.object(lichess.Lichess, "api_post", return_value={}),
        pytest.raises(RuntimeError, match="retrieving information about the bot's token"),
    ):
        lichess.Lichess("test-token", "https://lichess.org/", "0.0.0", logging.DEBUG, 3)


def test_init_rejects_token_without_bot_play_scope() -> None:
    """Initialization should fail when the token lacks the bot:play scope."""
    test_value = "test-token"
    token_response: TOKEN_TESTS_TYPE = {test_value: {"scopes": "challenge:read"}}

    with (
        patch.object(lichess.Lichess, "api_post", return_value=token_response),
        pytest.raises(RuntimeError, match="bot:play"),
    ):
        lichess.Lichess(test_value, "https://lichess.org/", "0.0.0", logging.DEBUG, 3)


def test_get_profile_returns_profile_and_sets_user_agent() -> None:
    """Profile data should be returned and used for the user agent."""
    li = lichess_without_init()
    profile: UserProfileType = {"username": "testbot", "perfs": {}}

    with (
        patch.object(li, "api_get_json", return_value=profile) as api_get_json,
        patch.object(li, "set_user_agent") as set_user_agent,
    ):
        assert li.get_profile() == profile

    api_get_json.assert_called_once_with("profile")
    set_user_agent.assert_called_once_with("testbot")


def test_get_ongoing_games_returns_now_playing() -> None:
    """The ongoing-games response should be unwrapped from nowPlaying."""
    li = lichess_without_init()
    game: GameType = {"gameId": "game-id", "isMyTurn": True}
    response: dict[str, list[GameType]] = {"nowPlaying": [game]}

    with patch.object(li, "api_get_json", return_value=response) as api_get_json:
        assert li.get_ongoing_games() == [game]

    api_get_json.assert_called_once_with("playing")


def test_get_ongoing_games_returns_none_on_error() -> None:
    """An API error while getting ongoing games should return None."""
    li = lichess_without_init()

    with patch.object(li, "api_get_json", side_effect=RuntimeError):
        assert li.get_ongoing_games() is None


def test_get_online_bots_parses_ndjson_and_ignores_empty_lines() -> None:
    """Online bots should be parsed from newline-delimited JSON."""
    li = lichess_without_init()
    response = '{"id":"bot-a","username":"BotA"}\n\n{"id":"bot-b","username":"BotB"}\n'
    expected: list[UserProfileType] = [
        {"id": "bot-a", "username": "BotA"},
        {"id": "bot-b", "username": "BotB"},
    ]

    with patch.object(li, "api_get_raw", return_value=response) as api_get_raw:
        assert li.get_online_bots() == expected

    api_get_raw.assert_called_once_with("online_bots", params={"nb": "512"})


def test_get_online_bots_returns_empty_list_on_error() -> None:
    """An API error while getting online bots should return an empty list."""
    li = lichess_without_init()

    with patch.object(li, "api_get_raw", side_effect=RuntimeError):
        assert li.get_online_bots() == []


@pytest.mark.parametrize(
    ("users", "expected"),
    [
        ([{"username": "testbot", "online": True}], True),
        ([{"username": "testbot", "online": False}], False),
        ([], False),
    ],
)
def test_is_online_uses_status_response(users: list[UserProfileType], expected: bool) -> None:
    """Online status should reflect the first returned user, or False if absent."""
    li = lichess_without_init()

    with patch.object(li, "api_get_list", return_value=users) as api_get_list:
        assert li.is_online("testbot") is expected

    api_get_list.assert_called_once_with("status", params={"ids": "testbot"})


def test_get_public_data_returns_user_data() -> None:
    """Public user data should be returned for the requested username."""
    li = lichess_without_init()
    public_data: PublicDataType = {"username": "opponent", "perfs": {}}

    with patch.object(li, "api_get_json", return_value=public_data) as api_get_json:
        assert li.get_public_data("opponent") == public_data

    api_get_json.assert_called_once_with("public_data", "opponent")


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
