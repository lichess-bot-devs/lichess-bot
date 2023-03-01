import json
import requests
from urllib.parse import urljoin
from requests.exceptions import ConnectionError, HTTPError, ReadTimeout
from http.client import RemoteDisconnected
import backoff
import logging
from collections import defaultdict
from timer import Timer
from typing import Optional, Dict, Union, Any, List, DefaultDict
import chess.engine
JSON_REPLY_TYPE = Dict[str, Any]
REQUESTS_PAYLOAD_TYPE = Dict[str, Any]

ENDPOINTS = {
    "profile": "/api/account",
    "playing": "/api/account/playing",
    "stream": "/api/bot/game/stream/{}",
    "stream_event": "/api/stream/event",
    "move": "/api/bot/game/{}/move/{}",
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
    "public_data": "/api/user/{}"
}


logger = logging.getLogger(__name__)

MAX_CHAT_MESSAGE_LEN = 140  # The maximum characters in a chat message.


class RateLimited(RuntimeError):
    pass


def is_new_rate_limit(response: requests.models.Response) -> bool:
    return response.status_code == 429


def is_final(exception: Exception) -> bool:
    return isinstance(exception, HTTPError) and exception.response.status_code < 500


# docs: https://lichess.org/api
class Lichess:
    def __init__(self, token: str, url: str, version: str, logging_level: int, max_retries: int) -> None:
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
        self.rate_limit_timers: DefaultDict[str, Timer] = defaultdict(Timer)

    @backoff.on_exception(backoff.constant,
                          (RemoteDisconnected, ConnectionError, HTTPError, ReadTimeout),
                          max_time=60,
                          interval=0.1,
                          giveup=is_final,
                          backoff_log_level=logging.DEBUG,
                          giveup_log_level=logging.DEBUG)
    def api_get(self, endpoint_name: str, *template_args: str,
                params: Optional[Dict[str, str]] = None) -> requests.Response:
        logging.getLogger("backoff").setLevel(self.logging_level)
        path_template = self.get_path_template(endpoint_name)
        url = urljoin(self.baseUrl, path_template.format(*template_args))
        response = self.session.get(url, params=params, timeout=2)

        if is_new_rate_limit(response):
            delay = 1 if endpoint_name == "move" else 60
            self.set_rate_limit_delay(path_template, delay)

        response.raise_for_status()
        response.encoding = "utf-8"
        return response

    def api_get_json(self, endpoint_name: str, *template_args: str,
                     params: Optional[Dict[str, str]] = None) -> JSON_REPLY_TYPE:
        response = self.api_get(endpoint_name, *template_args, params=params)
        json_response: JSON_REPLY_TYPE = response.json()
        return json_response

    def api_get_list(self, endpoint_name: str, *template_args: str,
                     params: Optional[Dict[str, str]] = None) -> List[JSON_REPLY_TYPE]:
        response = self.api_get(endpoint_name, *template_args, params=params)
        json_response: List[JSON_REPLY_TYPE] = response.json()
        return json_response

    def api_get_raw(self, endpoint_name: str, *template_args: str,
                    params: Optional[Dict[str, str]] = None, ) -> str:
        response = self.api_get(endpoint_name, *template_args, params=params)
        return response.text

    @backoff.on_exception(backoff.constant,
                          (RemoteDisconnected, ConnectionError, HTTPError, ReadTimeout),
                          max_time=60,
                          interval=0.1,
                          giveup=is_final,
                          backoff_log_level=logging.DEBUG,
                          giveup_log_level=logging.DEBUG)
    def api_post(self,
                 endpoint_name: str,
                 *template_args: Any,
                 data: Union[str, Dict[str, str], None] = None,
                 headers: Optional[Dict[str, str]] = None,
                 params: Optional[Dict[str, str]] = None,
                 payload: Optional[REQUESTS_PAYLOAD_TYPE] = None,
                 raise_for_status: bool = True) -> JSON_REPLY_TYPE:
        logging.getLogger("backoff").setLevel(self.logging_level)
        path_template = self.get_path_template(endpoint_name)
        url = urljoin(self.baseUrl, path_template.format(*template_args))
        response = self.session.post(url, data=data, headers=headers, params=params, json=payload, timeout=2)

        if is_new_rate_limit(response):
            self.set_rate_limit_delay(path_template, 60)

        if raise_for_status:
            response.raise_for_status()

        json_response: JSON_REPLY_TYPE = response.json()
        return json_response

    def get_path_template(self, endpoint_name: str) -> str:
        path_template = ENDPOINTS[endpoint_name]
        if self.is_rate_limited(path_template):
            raise RateLimited(f"{path_template} is rate-limited. "
                              f"Will retry in {int(self.rate_limit_time_left(path_template))} seconds.")
        return path_template

    def set_rate_limit_delay(self, path_template: str, delay_time: int) -> None:
        logger.warning(f"Endpoint {path_template} is rate limited. Waiting {delay_time} seconds until next request.")
        self.rate_limit_timers[path_template] = Timer(delay_time)

    def is_rate_limited(self, path_template: str) -> bool:
        return not self.rate_limit_timers[path_template].is_expired()

    def rate_limit_time_left(self, path_template: str) -> float:
        return self.rate_limit_timers[path_template].time_until_expiration()

    def upgrade_to_bot_account(self) -> JSON_REPLY_TYPE:
        return self.api_post("upgrade")

    def make_move(self, game_id: str, move: chess.engine.PlayResult) -> JSON_REPLY_TYPE:
        return self.api_post("move", game_id, move.move,
                             params={"offeringDraw": str(move.draw_offered).lower()})

    def chat(self, game_id: str, room: str, text: str) -> JSON_REPLY_TYPE:
        if len(text) > MAX_CHAT_MESSAGE_LEN:
            logger.warning(f"This chat message is {len(text)} characters, which is longer "
                           f"than the maximum of {MAX_CHAT_MESSAGE_LEN}. It will not be sent.")
            logger.warning(f"Message: {text}")
            return {}

        payload = {"room": room, "text": text}
        return self.api_post("chat", game_id, data=payload)

    def abort(self, game_id: str) -> JSON_REPLY_TYPE:
        return self.api_post("abort", game_id)

    def get_event_stream(self) -> requests.models.Response:
        url = urljoin(self.baseUrl, ENDPOINTS["stream_event"])
        return requests.get(url, headers=self.header, stream=True, timeout=15)

    def get_game_stream(self, game_id: str) -> requests.models.Response:
        url = urljoin(self.baseUrl, ENDPOINTS["stream"].format(game_id))
        return requests.get(url, headers=self.header, stream=True, timeout=15)

    def accept_challenge(self, challenge_id: str) -> JSON_REPLY_TYPE:
        return self.api_post("accept", challenge_id)

    def decline_challenge(self, challenge_id: str, reason: str = "generic") -> JSON_REPLY_TYPE:
        try:
            return self.api_post("decline", challenge_id,
                                 data=f"reason={reason}",
                                 headers={"Content-Type":
                                          "application/x-www-form-urlencoded"},
                                 raise_for_status=False)
        except Exception:
            return {}

    def get_profile(self) -> JSON_REPLY_TYPE:
        profile = self.api_get_json("profile")
        self.set_user_agent(profile["username"])
        return profile

    def get_ongoing_games(self) -> List[Dict[str, Any]]:
        ongoing_games: List[Dict[str, Any]] = []
        try:
            ongoing_games = self.api_get_json("playing")["nowPlaying"]
        except Exception:
            pass
        return ongoing_games

    def resign(self, game_id: str) -> None:
        self.api_post("resign", game_id)

    def set_user_agent(self, username: str) -> None:
        self.header.update({"User-Agent": f"lichess-bot/{self.version} user:{username}"})
        self.session.headers.update(self.header)

    def get_game_pgn(self, game_id: str) -> str:
        try:
            return self.api_get_raw("export", game_id)
        except Exception:
            return ""

    def get_online_bots(self) -> List[Dict[str, Any]]:
        try:
            online_bots_str = self.api_get_raw("online_bots")
            online_bots = list(filter(bool, online_bots_str.split("\n")))
            return list(map(json.loads, online_bots))
        except Exception:
            return []

    def challenge(self, username: str, payload: REQUESTS_PAYLOAD_TYPE) -> JSON_REPLY_TYPE:
        return self.api_post("challenge", username, payload=payload, raise_for_status=False)

    def cancel(self, challenge_id: str) -> JSON_REPLY_TYPE:
        return self.api_post("cancel", challenge_id, raise_for_status=False)

    def online_book_get(self, path: str, params: Optional[Dict[str, Any]] = None) -> JSON_REPLY_TYPE:
        @backoff.on_exception(backoff.constant,
                              (RemoteDisconnected, ConnectionError, HTTPError, ReadTimeout),
                              max_time=60,
                              max_tries=self.max_retries,
                              interval=0.1,
                              giveup=is_final,
                              backoff_log_level=logging.DEBUG,
                              giveup_log_level=logging.DEBUG)
        def online_book_get() -> JSON_REPLY_TYPE:
            json_response: JSON_REPLY_TYPE = self.other_session.get(path, timeout=2, params=params).json()
            return json_response
        return online_book_get()

    def is_online(self, user_id: str) -> bool:
        user = self.api_get_list("status", params={"ids": user_id})
        return bool(user and user[0].get("online"))

    def get_public_data(self, user_name: str) -> JSON_REPLY_TYPE:
        return self.api_get_json("public_data", user_name)
