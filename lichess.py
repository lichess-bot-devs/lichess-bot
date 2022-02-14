import requests
from urllib.parse import urljoin
from requests.exceptions import ConnectionError, HTTPError, ReadTimeout
from urllib3.exceptions import ProtocolError
from http.client import RemoteDisconnected
import backoff
import logging

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
    "resign": "/api/bot/game/{}/resign"
}


# docs: https://lichess.org/api
class Lichess:
    def __init__(self, token, url, version, logging_level):
        self.version = version
        self.header = {
            "Authorization": f"Bearer {token}"
        }
        self.baseUrl = url
        self.session = requests.Session()
        self.session.headers.update(self.header)
        self.set_user_agent("?")
        self.logging_level = logging_level

    def is_final(exception):
        return isinstance(exception, HTTPError) and exception.response.status_code < 500

    @backoff.on_exception(backoff.constant,
                          (RemoteDisconnected, ConnectionError, ProtocolError, HTTPError, ReadTimeout),
                          max_time=60,
                          interval=0.1,
                          giveup=is_final,
                          backoff_log_level=logging.DEBUG,
                          giveup_log_level=logging.DEBUG)
    def api_get(self, path, raise_for_status=True):
        logging.getLogger("backoff").setLevel(self.logging_level)
        url = urljoin(self.baseUrl, path)
        response = self.session.get(url, timeout=2)
        if raise_for_status:
            response.raise_for_status()
        return response.json()

    @backoff.on_exception(backoff.constant,
                          (RemoteDisconnected, ConnectionError, ProtocolError, HTTPError, ReadTimeout),
                          max_time=60,
                          interval=0.1,
                          giveup=is_final,
                          backoff_log_level=logging.DEBUG,
                          giveup_log_level=logging.DEBUG)
    def api_post(self, path, data=None, headers=None, params=None):
        logging.getLogger("backoff").setLevel(self.logging_level)
        url = urljoin(self.baseUrl, path)
        response = self.session.post(url, data=data, headers=headers, params=params, timeout=2)
        response.raise_for_status()
        return response.json()

    def get_game(self, game_id):
        return self.api_get(ENDPOINTS["game"].format(game_id))

    def upgrade_to_bot_account(self):
        return self.api_post(ENDPOINTS["upgrade"])

    def make_move(self, game_id, move):
        return self.api_post(ENDPOINTS["move"].format(game_id, move.move),
                             params={"offeringDraw": str(move.draw_offered).lower()})

    def chat(self, game_id, room, text):
        payload = {"room": room, "text": text}
        return self.api_post(ENDPOINTS["chat"].format(game_id), data=payload)

    def abort(self, game_id):
        return self.api_post(ENDPOINTS["abort"].format(game_id))

    def get_event_stream(self):
        url = urljoin(self.baseUrl, ENDPOINTS["stream_event"])
        return requests.get(url, headers=self.header, stream=True)

    def get_game_stream(self, game_id):
        url = urljoin(self.baseUrl, ENDPOINTS["stream"].format(game_id))
        return requests.get(url, headers=self.header, stream=True)

    def accept_challenge(self, challenge_id):
        return self.api_post(ENDPOINTS["accept"].format(challenge_id))

    def decline_challenge(self, challenge_id, reason="generic"):
        return self.api_post(ENDPOINTS["decline"].format(challenge_id), data=f"reason={reason}", headers={"Content-Type": "application/x-www-form-urlencoded"})

    def get_profile(self):
        profile = self.api_get(ENDPOINTS["profile"])
        self.set_user_agent(profile["username"])
        return profile

    def get_ongoing_games(self):
        ongoing_games = self.api_get(ENDPOINTS["playing"])["nowPlaying"]
        return ongoing_games

    def resign(self, game_id):
        self.api_post(ENDPOINTS["resign"].format(game_id))

    def set_user_agent(self, username):
        self.header.update({"User-Agent": f"lichess-bot/{self.version} user:{username}"})
        self.session.headers.update(self.header)
