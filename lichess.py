import json
import requests

ENDPOINTS = {
    "profile": "account/me",
    "stream": "bot/game/stream/{}",
    "game": "bot/game/{}",
    "move": "bot/game/{}/move/{}",
    "upgrade": "bot/account/upgrade"
}

# docs: https://lichess.org/api
class Lichess():

    def __init__(self, token, url):
        self.header = self._get_header(token)
        self.baseUrl = url
        self._test()


    def _test(self):
        url = self.baseUrl + ENDPOINTS["profile"]
        r = requests.get(url, headers=self.header)

        if r.status_code != 200:
            print("Invalid token!")
            print(r.text)
        else:
            print("Valid token!")


    def get_game(self, game_id):
        url = self.baseUrl + ENDPOINTS["game"].format(game_id)
        r = requests.get(url, headers=self.header)

        if r.status_code != 200:
            print("Something went wrong! status_code: {}, response: {}".format(r.status_code, r.text))
            return None

        return r.json()


    def upgrade_to_bot_account(self):
        url = self.baseUrl + ENDPOINTS["upgrade"]
        r = requests.post(url, headers=self.header)

        if r.status_code != 200:
            print("Something went wrong! status_code: {}, response: {}".format(r.status_code, r.text))
            return None

        return r.json()

    def make_move(self, game_id, move):
        url = self.baseUrl + ENDPOINTS["move"].format(game_id, move)
        r = requests.post(url, headers=self.header)

        if r.status_code != 200:
            print("Something went wrong! status_code: {}, response: {}".format(r.status_code, r.text))
            return None

        return r.json()


    def get_stream(self, game_id):
        url = self.baseUrl + ENDPOINTS["stream"].format(game_id)
        return requests.get(url, headers=self.header, stream=True)



    def get_profile(self):
        url = self.baseUrl + ENDPOINTS["profile"]
        r = requests.get(url, headers=self.header)
        if r.status_code != 200:
            print("Something went wrong! status_code: {}, response: {}".format(r.status_code, r.text))
            return None

        return r.json()


    def _get_header(self, token):
        header = {
            "Authorization": "Bearer {}".format(token)
        }

        return header
