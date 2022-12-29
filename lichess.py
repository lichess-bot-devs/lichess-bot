import json
import requests
from urllib.parse import urljoin
from requests.exceptions import ConnectionError, HTTPError, ReadTimeout
from http.client import RemoteDisconnected
import backoff
import logging
from collections import defaultdict
from engine_wrapper import MAX_CHAT_MESSAGE_LEN
from timer import Timer

ENDPOINTS = {
    "profile": "/api/account",
    "playing": "/api/account/playing",
    "stream": "/api/bot/game/stream/{}",
    "stream_event": "/api/stream/event",
    "game": "/api/bot/game/{}",
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


class RateLimited(RuntimeError):
    pass


def is_new_rate_limit(response):
    return response.status_code == 429


# docs: https://lichess.org/api
class Lichess:
    def __init__(self, token, url, version, logging_level, max_retries):
        self.version = version
        self.header = {
            "Authorization": f"Bearer {token}"
        }
        self.baseUrl = url
        self.session = requests.Session()
        self.session.headers.update(self.header)
        self.set_user_agent("?")
        self.logging_level = logging_level
        self.max_retries = max_retries
        self.rate_limit_timers = defaultdict(Timer)

    def is_final(exception):
        return isinstance(exception, HTTPError) and exception.response.status_code < 500

    @backoff.on_exception(backoff.constant,
                          (RemoteDisconnected, ConnectionError, HTTPError, ReadTimeout),
                          max_time=60,
                          interval=0.1,
                          giveup=is_final,
                          backoff_log_level=logging.DEBUG,
                          giveup_log_level=logging.DEBUG)
    def api_get(self, endpoint_name, *template_args, params=None, get_raw_text=False):
        logging.getLogger("backoff").setLevel(self.logging_level)

        path_template = ENDPOINTS[endpoint_name]
        if self.is_rate_limited(path_template):
            raise RateLimited(f"{path_template} is rate-limited. "
                              f"Will retry in {int(self.rate_limit_time_left(path_template))} seconds.")

        url = urljoin(self.baseUrl, path_template.format(*template_args))
        response = self.session.get(url, params=params, timeout=2)

        if is_new_rate_limit(response):
            logger.warning("Rate limited. Waiting 1 minute until next request.")
            delay = 1 if endpoint_name == "move" else 60
            self.rate_limit_timers[path_template] = Timer(delay)

        response.raise_for_status()
        response.encoding = "utf-8"
        return response.text if get_raw_text else response.json()

    @backoff.on_exception(backoff.constant,
                          (RemoteDisconnected, ConnectionError, HTTPError, ReadTimeout),
                          max_time=60,
                          interval=0.1,
                          giveup=is_final,
                          backoff_log_level=logging.DEBUG,
                          giveup_log_level=logging.DEBUG)
    def api_post(self,
                 endpoint_name,
                 *template_args,
                 data=None,
                 headers=None,
                 params=None,
                 payload=None,
                 raise_for_status=True):
        logging.getLogger("backoff").setLevel(self.logging_level)

        path_template = ENDPOINTS[endpoint_name]
        if self.is_rate_limited(path_template):
            raise RateLimited(f"{path_template} is rate-limited. "
                              f"Will retry in {int(self.rate_limit_time_left(path_template))} seconds.")

        url = urljoin(self.baseUrl, path_template.format(*template_args))
        response = self.session.post(url, data=data, headers=headers, params=params, json=payload, timeout=2)

        if is_new_rate_limit(response):
            logger.warning("Rate limited. Waiting 1 minute until next request.")
            self.rate_limit_timers[path_template] = Timer(60)

        if raise_for_status:
            response.raise_for_status()

        return response.json()

    def is_rate_limited(self, path_template):
        return not self.rate_limit_timers[path_template].is_expired()

    def rate_limit_time_left(self, path_template):
        return self.rate_limit_time_left[path_template].time_until_expiration()

    def get_game(self, game_id):
        return self.api_get("game", game_id)

    def upgrade_to_bot_account(self):
        return self.api_post("upgrade")

    def make_move(self, game_id, move):
        return self.api_post("move", game_id, move.move,
                             params={"offeringDraw": str(move.draw_offered).lower()})

    def chat(self, game_id, room, text):
        if len(text) > MAX_CHAT_MESSAGE_LEN:
            logger.warn(f"This chat message is {len(text)} characters, which is longer "
                        f"than the maximum of {MAX_CHAT_MESSAGE_LEN}. It will not be sent.")
            logger.warn(f"Message: {text}")
            return {}

        payload = {"room": room, "text": text}
        return self.api_post("chat", game_id, data=payload)

    def abort(self, game_id):
        return self.api_post("abort", game_id)

    def get_event_stream(self):
        url = urljoin(self.baseUrl, ENDPOINTS["stream_event"])
        return requests.get(url, headers=self.header, stream=True, timeout=15)

    def get_game_stream(self, game_id):
        url = urljoin(self.baseUrl, ENDPOINTS["stream"].format(game_id))
        return requests.get(url, headers=self.header, stream=True, timeout=15)

    def accept_challenge(self, challenge_id):
        return self.api_post("accept", challenge_id)

    def decline_challenge(self, challenge_id, reason="generic"):
        return self.api_post("decline", challenge_id,
                             data=f"reason={reason}",
                             headers={"Content-Type":
                                      "application/x-www-form-urlencoded"},
                             raise_for_status=False)

    def get_profile(self):
        profile = self.api_get("profile")
        self.set_user_agent(profile["username"])
        return profile

    def get_ongoing_games(self):
        try:
            return self.api_get("playing")["nowPlaying"]
        except Exception:
            return []

    def resign(self, game_id):
        self.api_post("resign", game_id)

    def set_user_agent(self, username):
        self.header.update({"User-Agent": f"lichess-bot/{self.version} user:{username}"})
        self.session.headers.update(self.header)

    def get_game_pgn(self, game_id):
        return self.api_get("export", game_id, get_raw_text=True)

    def get_online_bots(self):
        try:
            online_bots = self.api_get("online_bots", get_raw_text=True)
            online_bots = list(filter(bool, online_bots.split("\n")))
            return list(map(json.loads, online_bots))
        except Exception:
            return []

    def challenge(self, username, params):
        return self.api_post("challenge", username, payload=params, raise_for_status=False)

    def cancel(self, challenge_id):
        return self.api_post("cancel", challenge_id, raise_for_status=False)

    def online_book_get(self, path, params=None):
        @backoff.on_exception(backoff.constant,
                              (RemoteDisconnected, ConnectionError, HTTPError, ReadTimeout),
                              max_time=60,
                              max_tries=self.max_retries,
                              interval=0.1,
                              giveup=self.is_final,
                              backoff_log_level=logging.DEBUG,
                              giveup_log_level=logging.DEBUG)
        def online_book_get():
            return self.session.get(path, timeout=2, params=params).json()
        return online_book_get()

    def is_online(self, user_id):
        user = self.api_get("status", params={"ids": user_id})
        return user and user[0].get("online")

    def get_public_data(self, user_name):
        return self.api_get("public_data", user_name)
