"""Communication with APIs."""
import json
import requests
from urllib.parse import urljoin
from requests.exceptions import ConnectionError as RequestsConnectionError, HTTPError, ReadTimeout
from http.client import RemoteDisconnected
import backoff
import logging
import traceback
from collections import defaultdict
import datetime
import contextlib
from lib.timer import Timer, seconds, sec_str
from typing import Optional, Union, cast
import chess.engine
from lib.lichess_types import (UserProfileType, REQUESTS_PAYLOAD_TYPE, GameType, PublicDataType, OnlineType,
                       ChallengeType, TOKEN_TESTS_TYPE, BackoffDetails)


ENDPOINTS = {
    "profile": "/api/account",
    "playing": "/api/account/playing",
    "stream": "/api/bot/game/stream/{}",
    "stream_event": "/api/stream/event",
    "move": "/api/bot/game/{}/move/{}",
    "takeback": "/api/bot/game/{}/takeback/{}",
    "chat": "/api/bot/game/{}/chat",
    "abort": "/api/bot/game/{}/abort",
    "accept": "/api/challenge/{}/accept",
    "decline": "/api/challenge/{}/decline",
    "upgrade": "/api/bot/account/upgrade",
    "resign": "/api/bot/game/{}/resign",
    "export": "/game/export/{}",
    "online_bots": "/api/bot/online",
    "challenge": "/api/challenge/{}",
    "cancel": "/api/challenge/{}/cancel",
    "status": "/api/users/status",
    "public_data": "/api/user/{}",
    "token_test": "/api/token/test"
}


logger = logging.getLogger(__name__)

MAX_CHAT_MESSAGE_LEN = 140  # The maximum characters in a chat message.


class RateLimitedError(RuntimeError):
    """Exception raised when we are rate limited (status code 429)."""


def is_new_rate_limit(response: requests.models.Response) -> bool:
    """Check if the status code is 429, which means that we are rate limited."""
    return response.status_code == 429


def is_final(exception: Exception) -> bool:
    """If `is_final` returns True then we won't retry."""
    return isinstance(exception, HTTPError) and exception.response is not None and exception.response.status_code < 500


def backoff_handler(details: BackoffDetails) -> None:
    """Log exceptions inside functions with the backoff decorator."""
    logger.debug("Backing off {wait:0.1f} seconds after {tries} tries "
                 "calling function {target} with args {args} and kwargs {kwargs}".format(**details))
    logger.debug(f"Exception: {traceback.format_exc()}")


# Docs: https://lichess.org/api.
class Lichess:
    """Communication with lichess.org (and chessdb.cn for getting moves)."""

    def __init__(self, token: str, url: str, version: str, logging_level: int, max_retries: int) -> None:
        """
        Communication with lichess.org (and chessdb.cn for getting moves).

        :param token: The bot's token.
        :param url: The base url (lichess.org).
        :param version: The lichess-bot version running.
        :param logging_level: The logging level (logging.INFO or logging.DEBUG).
        :param max_retries: The maximum amount of retries for online moves (e.g. chessdb's opening book).
        """
        self.version = version
        self.header = {
            "Authorization": f"Bearer {token}"
        }
        self.baseUrl = url
        self.session = requests.Session()
        self.session.headers.update(self.header)
        self.other_session = requests.Session()
        self.set_user_agent("?")
        self.logging_level = logging_level
        self.max_retries = max_retries
        self.rate_limit_timers: defaultdict[str, Timer] = defaultdict(Timer)

        # Confirm that the OAuth token has the proper permission to play on lichess
        token_response = cast(TOKEN_TESTS_TYPE, self.api_post("token_test", data=token))
        token_info = token_response[token]

        if not token_info:
            raise RuntimeError("Token in config file is not recognized by lichess. "
                               "Please check that it was copied correctly into your configuration file.")

        scopes = token_info["scopes"]
        if "bot:play" not in scopes.split(","):
            raise RuntimeError("Please use an API access token for your bot that "
                               'has the scope "Play games with the bot API (bot:play)". '
                               f"The current token has: {scopes}.")

    @backoff.on_exception(backoff.constant,
                          (RemoteDisconnected, RequestsConnectionError, HTTPError, ReadTimeout),
                          max_time=60,
                          interval=0.1,
                          giveup=is_final,
                          on_backoff=backoff_handler,
                          backoff_log_level=logging.DEBUG,
                          giveup_log_level=logging.DEBUG)
    def api_get(self, endpoint_name: str, *template_args: str,
                params: Optional[dict[str, str]] = None,
                stream: bool = False, timeout: int = 2) -> requests.Response:
        """
        Send a GET to lichess.org.

        :param endpoint_name: The name of the endpoint.
        :param template_args: The values that go in the url (e.g. the challenge id if `endpoint_name` is `accept`).
        :param params: Parameters sent to lichess.org.
        :param stream: Whether the data returned from lichess.org should be streamed.
        :param timeout: The amount of time in seconds to wait for a response.
        :return: lichess.org's response.
        """
        logging.getLogger("backoff").setLevel(self.logging_level)
        path_template = self.get_path_template(endpoint_name)
        url = urljoin(self.baseUrl, path_template.format(*template_args))
        response = self.session.get(url, params=params, timeout=timeout, stream=stream)

        if is_new_rate_limit(response):
            delay = seconds(1 if endpoint_name == "move" else 60)
            self.set_rate_limit_delay(path_template, delay)

        response.raise_for_status()
        response.encoding = "utf-8"
        return response

    def api_get_json(self, endpoint_name: str, *template_args: str,
                     params: Optional[dict[str, str]] = None
                     ) -> Union[PublicDataType, UserProfileType, dict[str, list[GameType]]]:
        """
        Send a GET to the lichess.org endpoints that return a JSON.

        :param endpoint_name: The name of the endpoint.
        :param template_args: The values that go in the url (e.g. the challenge id if `endpoint_name` is `accept`).
        :param params: Parameters sent to lichess.org.
        :return: lichess.org's response in a dict.
        """
        response = self.api_get(endpoint_name, *template_args, params=params)
        json_response: Union[PublicDataType, UserProfileType, dict[str, list[GameType]]] = response.json()
        return json_response

    def api_get_list(self, endpoint_name: str, *template_args: str,
                     params: Optional[dict[str, str]] = None) -> list[UserProfileType]:
        """
        Send a GET to the lichess.org endpoints that return a list containing JSON.

        :param endpoint_name: The name of the endpoint.
        :param template_args: The values that go in the url (e.g. the challenge id if `endpoint_name` is `accept`).
        :param params: Parameters sent to lichess.org.
        :return: lichess.org's response in a list of dicts.
        """
        response = self.api_get(endpoint_name, *template_args, params=params)
        json_response: list[UserProfileType] = response.json()
        return json_response

    def api_get_raw(self, endpoint_name: str, *template_args: str,
                    params: Optional[dict[str, str]] = None) -> str:
        """
        Send a GET to lichess.org that returns plain text (UTF-8).

        :param endpoint_name: The name of the endpoint.
        :param template_args: The values that go in the url (e.g. the challenge id if `endpoint_name` is `accept`).
        :param params: Parameters sent to lichess.org.
        :return: The text of lichess.org's response.
        """
        response = self.api_get(endpoint_name, *template_args, params=params)
        return response.text

    @backoff.on_exception(backoff.constant,
                          (RemoteDisconnected, RequestsConnectionError, HTTPError, ReadTimeout),
                          max_time=60,
                          interval=0.1,
                          giveup=is_final,
                          on_backoff=backoff_handler,
                          backoff_log_level=logging.DEBUG,
                          giveup_log_level=logging.DEBUG)
    def api_post(self,
                 endpoint_name: str,
                 *template_args: str,
                 data: Union[str, dict[str, str], None] = None,
                 headers: Optional[dict[str, str]] = None,
                 params: Optional[dict[str, str]] = None,
                 payload: Optional[REQUESTS_PAYLOAD_TYPE] = None,
                 raise_for_status: bool = True) -> Union[ChallengeType, Optional[TOKEN_TESTS_TYPE]]:
        """
        Send a POST to lichess.org.

        :param endpoint_name: The name of the endpoint.
        :param template_args: The values that go in the url (e.g. the challenge id if `endpoint_name` is `accept`).
        :param data: Data sent to lichess.org.
        :param headers: The headers for the request.
        :param params: Parameters sent to lichess.org.
        :param payload: Payload sent to lichess.org.
        :param raise_for_status: Whether to raise an exception if the response contains an error code.
        :return: lichess.org's response in a dict.
        """
        logging.getLogger("backoff").setLevel(self.logging_level)
        path_template = self.get_path_template(endpoint_name)
        url = urljoin(self.baseUrl, path_template.format(*template_args))
        response = self.session.post(url, data=data, headers=headers, params=params, json=payload, timeout=2)

        if is_new_rate_limit(response):
            self.set_rate_limit_delay(path_template, seconds(60))

        if raise_for_status:
            response.raise_for_status()

        json_response: Union[ChallengeType, Optional[TOKEN_TESTS_TYPE]] = response.json()
        return json_response

    def get_path_template(self, endpoint_name: str) -> str:
        """
        Get the path template given the endpoint name. Will raise an exception if the path template is rate limited.

        :param endpoint_name: The name of the endpoint.
        :return: The path template.
        """
        path_template = ENDPOINTS[endpoint_name]
        if self.is_rate_limited(path_template):
            raise RateLimitedError(f"{path_template} is rate-limited. "
                                   f"Will retry in {sec_str(self.rate_limit_time_left(path_template))} seconds.")
        return path_template

    def set_rate_limit_delay(self, path_template: str, delay_time: datetime.timedelta) -> None:
        """
        Set a delay to a path template if it was rate limited.

        :param path_template: The path template.
        :param delay_time: How long we won't call this endpoint.
        """
        logger.warning(f"Endpoint {path_template} is rate limited. Waiting {sec_str(delay_time)} seconds until next request.")
        self.rate_limit_timers[path_template] = Timer(delay_time)

    def is_rate_limited(self, path_template: str) -> bool:
        """Check if a path template is rate limited."""
        return not self.rate_limit_timers[path_template].is_expired()

    def rate_limit_time_left(self, path_template: str) -> datetime.timedelta:
        """How much time is left until we can use the path template normally."""
        return self.rate_limit_timers[path_template].time_until_expiration()

    def upgrade_to_bot_account(self) -> None:
        """Upgrade the account to a BOT account."""
        self.api_post("upgrade")

    def make_move(self, game_id: str, move: chess.engine.PlayResult) -> None:
        """
        Make a move.

        :param game_id: The id of the game.
        :param move: The move to make.
        """
        self.api_post("move", game_id, str(move.move),
                      params={"offeringDraw": str(move.draw_offered).lower()})

    def accept_takeback(self, game_id: str, accept: bool) -> bool:
        """Answer an opponent's move takeback request."""
        try:
            self.api_post("takeback", game_id, "yes" if accept else "no")
            if accept:
                logger.info("Opponent took back previous move.")
            else:
                logger.info("Refused opponent's take back request.")
            return accept
        except Exception:
            return False

    def chat(self, game_id: str, room: str, text: str) -> None:
        """
        Send a message to the chat.

        :param game_id: The id of the game.
        :param room: The room (either chat or spectator room).
        :param text: The text to send.
        """
        if len(text) > MAX_CHAT_MESSAGE_LEN:
            logger.warning(f"This chat message is {len(text)} characters, which is longer "
                           f"than the maximum of {MAX_CHAT_MESSAGE_LEN}. It will not be sent.")
            logger.warning(f"Message: {text}")

        data = {"room": room, "text": text}
        self.api_post("chat", game_id, data=data)

    def abort(self, game_id: str) -> None:
        """Aborts a game."""
        self.api_post("abort", game_id)

    def get_event_stream(self) -> requests.models.Response:
        """Get a stream of the events (e.g. challenge, gameStart)."""
        return self.api_get("stream_event", stream=True, timeout=15)

    def get_game_stream(self, game_id: str) -> requests.models.Response:
        """Get  stream of the in-game events (e.g. moves by the opponent)."""
        return self.api_get("stream", game_id, stream=True, timeout=15)

    def accept_challenge(self, challenge_id: str) -> None:
        """Accept a challenge."""
        self.api_post("accept", challenge_id)

    def decline_challenge(self, challenge_id: str, reason: str = "generic") -> None:
        """Decline a challenge."""
        with contextlib.suppress(Exception):
            self.api_post("decline", challenge_id,
                          data=f"reason={reason}",
                          headers={"Content-Type": "application/x-www-form-urlencoded"},
                          raise_for_status=False)

    def get_profile(self) -> UserProfileType:
        """Get the bot's profile (e.g. username)."""
        profile = cast(UserProfileType, self.api_get_json("profile"))
        self.set_user_agent(profile["username"])
        return profile

    def get_ongoing_games(self) -> list[GameType]:
        """Get the bot's ongoing games."""
        ongoing_games: list[GameType] = []
        with contextlib.suppress(Exception):
            response = cast(dict[str, list[GameType]], self.api_get_json("playing"))
            ongoing_games = response["nowPlaying"]
        return ongoing_games

    def resign(self, game_id: str) -> None:
        """Resign a game."""
        self.api_post("resign", game_id)

    def set_user_agent(self, username: str) -> None:
        """Set the user agent for communication with lichess.org."""
        self.header.update({"User-Agent": f"lichess-bot/{self.version} user:{username}"})
        self.session.headers.update(self.header)

    def get_game_pgn(self, game_id: str) -> str:
        """Get the PGN (Portable Game Notation) record of a game."""
        try:
            return self.api_get_raw("export", game_id)
        except Exception:
            return ""

    def get_online_bots(self) -> list[UserProfileType]:
        """Get a list of bots that are online."""
        try:
            online_bots_str = self.api_get_raw("online_bots")
            online_bots = list(filter(bool, online_bots_str.split("\n")))
            return list(map(json.loads, online_bots))
        except Exception:
            return []

    def challenge(self, username: str, payload: REQUESTS_PAYLOAD_TYPE) -> ChallengeType:
        """Create a challenge."""
        return cast(ChallengeType,
                    self.api_post("challenge", username, payload=payload, raise_for_status=False))

    def cancel(self, challenge_id: str) -> None:
        """Cancel a challenge."""
        self.api_post("cancel", challenge_id, raise_for_status=False)

    def online_book_get(self, path: str, params: Optional[dict[str, Union[str, int]]] = None,
                        stream: bool = False) -> OnlineType:
        """Get an external move from online sources (chessdb or lichess.org)."""
        @backoff.on_exception(backoff.constant,
                              (RemoteDisconnected, RequestsConnectionError, HTTPError, ReadTimeout),
                              max_time=60,
                              max_tries=self.max_retries,
                              interval=0.1,
                              giveup=is_final,
                              on_backoff=backoff_handler,
                              backoff_log_level=logging.DEBUG,
                              giveup_log_level=logging.DEBUG)
        def online_book_get() -> OnlineType:
            json_response: OnlineType = self.other_session.get(path, timeout=2, params=params, stream=stream).json()
            return json_response
        return online_book_get()

    def is_online(self, user_id: str) -> bool:
        """Check if lichess.org thinks the bot is online or not."""
        user = self.api_get_list("status", params={"ids": user_id})
        return bool(user and user[0].get("online"))

    def get_public_data(self, user_name: str) -> PublicDataType:
        """Get the public data of a bot."""
        return cast(PublicDataType, self.api_get_json("public_data", user_name))
