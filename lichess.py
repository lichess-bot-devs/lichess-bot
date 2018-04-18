import json
import requests
from future.standard_library import install_aliases
install_aliases()
from urllib.parse import urlparse, urlencode
from urllib.parse import urljoin

ENDPOINTS = {
    "profile": "/account/me",
    "stream": "/bot/game/stream/{}",
    "stream_event": "/api/stream/event",
    "game": "/bot/game/{}",
    "move": "/bot/game/{}/move/{}",
    "accept": "/challenge/{}/accept",
    "decline": "/challenge/{}/decline",
    "upgrade": "/bot/account/upgrade"
}

# docs: https://lichess.org/api
class Lichess():

    def __init__(self, token, url):
        self.header = self._get_header(token)
        self.baseUrl = url

    def get_json(self, response):
        if response.status_code != 200:
            print("Something went wrong! status_code: {}, response: {}".format(response.status_code, response.text))
            return None
        return response.json()

    def get_game(self, game_id):
        url = urljoin(self.baseUrl, ENDPOINTS["game"].format(game_id))
        return self.get_json(requests.get(url, headers=self.header))


    def upgrade_to_bot_account(self):
        url = urljoin(self.baseUrl, ENDPOINTS["upgrade"])
        return self.get_json(requests.post(url, headers=self.header))


    def make_move(self, game_id, move):
        url = urljoin(self.baseUrl, ENDPOINTS["move"].format(game_id, move))
        return self.get_json(requests.post(url, headers=self.header))


    def get_stream(self, game_id):
        url = urljoin(self.baseUrl, ENDPOINTS["stream"].format(game_id))
        return requests.get(url, headers=self.header, stream=True)


    def get_event_stream(self):
        url = self.baseUrl + ENDPOINTS["stream_event"]
        return requests.get(url, headers=self.header, stream=True)


    def accept_challenge(self, challenge_id):
        url = urljoin(self.baseUrl, ENDPOINTS["accept"].format(challenge_id))
        return self.get_json(requests.post(url, headers=self.header))


    def decline_challenge(self, challenge_id):
        url = urljoin(self.baseUrl, ENDPOINTS["decline"].format(challenge_id))
        return self.get_json(requests.post(url, headers=self.header))


    def get_profile(self):
        url = urljoin(self.baseUrl, ENDPOINTS["profile"])
        return self.get_json(requests.get(url, headers=self.header))


    def _get_header(self, token):
        return {
            "Authorization": "Bearer {}".format(token)
        }
