import json
import requests
from enum import Enum


class PerfType(Enum):
    bullet = 1
    blitz = 2
    rapid = 3
    classical = 4
    ultraBullet = 5

    chess960 = 6
    crazyhouse = 7
    antichess = 8
    atomic = 9
    horde = 10
    kingOfTheHill = 11
    racingKings = 12
    threeCheck = 13


BASEURL = "https://listage.ovh{}"

ENDPOINTS = {
    "profile": "/account/me",
    "email": "/account/email",
    "preferences": "/account/preferences",
    "kid": "/account/kid",
    "stream": "/bot/game/stream/{}",
    "game": "/bot/game/{}",
    "move": "/bot/game/{}/move/{}",
    "status": "/api/users/status",
    "player": "/player",
    "user": "/api/user/{}",
    "users": "/api/users/",
    "team": "/team/{}/users",
    "activity": "/api/user/{}/activity",
    "export": "/game/export/{}.pgn"
}

SCOPES = {
    "read_game": "game:read",
    "read_pref": "preference:read",
    "write_pref": "preference:write",
    "bot_play": "bot:play",
    "read_email": "email:read"
}

# docs: https://lichess.org/api
class Lichess():

    def __init__(self, token):
        self.header = self._get_header(token)
        self._test()


    def _test(self):
        url = BASEURL.format(ENDPOINTS["profile"])
        r = requests.get(url, headers=self.header)

        if r.status_code != 200:
            print("Invalid token!")
            print(r.text)
        else:
            print("Valid token!")


    def get_email(self):
        url = BASEURL.format(ENDPOINTS["email"])
        r = requests.get(url, headers=self.header)

        if r.status_code != 200:
            print("Something went wrong! status_code: {}, response: {}".format(r.status_code, r.text))
            return None

        return r.json()


    def get_real_time_users_status(self, ids):
        url = BASEURL.format(ENDPOINTS["status"])
        r = requests.get(url, params={"ids": ids})

        if r.status_code != 200:
            print("Something went wrong! status_code: {}, response: {}".format(r.status_code, r.text))
            return None

        return r.json()


    def get_all_top_10(self):
        url = BASEURL.format(ENDPOINTS["player"])
        headers = {"Accept": "application/vnd.lichess.v3+json"}
        r = requests.get(url, headers=headers)

        if r.status_code != 200:
            print("Something went wrong! status_code: {}, response: {}".format(r.status_code, r.text))
            return None

        return r.json()


    def get_one_leaderboard(self, nb, perf_type):
        url = BASEURL.format(ENDPOINTS["player"])
        headers = {"Accept": "application/vnd.lichess.v3+json"}
        r = requests.get(url, headers=headers, params={"nb": nb, "perfType": perf_type.name})

        if r.status_code != 200:
            print("Something went wrong! status_code: {}, response: {}".format(r.status_code, r.text))
            return None

        return r.json()


    def get_user_public_data(self, username):
        url = BASEURL.format(ENDPOINTS["user"])
        r = requests.get(url, params={"username": username})

        if r.status_code != 200:
            print("Something went wrong! status_code: {}, response: {}".format(r.status_code, r.text))
            return None

        return r.json()


    def get_user_activity(self, username):
        url = BASEURL.format(ENDPOINTS["activity"])
        r = requests.get(url, params={"username": username})

        if r.status_code != 200:
            print("Something went wrong! status_code: {}, response: {}".format(r.status_code, r.text))
            return None

        return r.json()


    def get_users_by_id(self, ids):
        url = BASEURL.format(ENDPOINTS["users"])
        r = requests.post(url, data=ids)

        if r.status_code != 200:
            print("Something went wrong! status_code: {}, response: {}".format(r.status_code, r.text))
            return None

        return r.json()


    def get_members_of_team(self, team_id, max=""):
        url = BASEURL.format(ENDPOINTS["team"].format(team_id))
        r = requests.get(url, params={"max": max})

        if r.status_code != 200:
            print("Something went wrong! status_code: {}, response: {}".format(r.status_code, r.text))
            return None

        return r.json()


    def get_game(self, game_id):
        url = BASEURL.format(ENDPOINTS["game"].format(game_id))
        r = requests.get(url, headers=self.header)

        if r.status_code != 200:
            print("Something went wrong! status_code: {}, response: {}".format(r.status_code, r.text))
            return None

        return r.json()


    def get_preferences(self):
        url = BASEURL.format(ENDPOINTS["preferences"])
        r = requests.get(url, headers=self.header)

        if r.status_code != 200:
            print("Something went wrong! status_code: {}, response: {}".format(r.status_code, r.text))
            return None

        return r.json()


    def get_kid_mode(self):
        url = BASEURL.format(ENDPOINTS["kid"])
        r = requests.get(url, headers=self.header)

        if r.status_code != 200:
            print("Something went wrong! status_code: {}, response: {}".format(r.status_code, r.text))
            return None

        return r.json()


    def set_kid_mode(self, kid_mode):
        url = BASEURL.format(ENDPOINTS["kid"])
        r = requests.post(url, headers=self.header, data={"v": kid_mode})

        if r.status_code != 200:
            print("Something went wrong! status_code: {}, response: {}".format(r.status_code, r.text))
            return None

        return r.json()


    def make_move(self, game_id, move):
        url = BASEURL.format(ENDPOINTS["move"].format(game_id, move))
        r = requests.post(url, headers=self.header)

        if r.status_code != 200:
            print("Something went wrong! status_code: {}, response: {}".format(r.status_code, r.text))
            return None

        return r.json()


    def get_stream(self, game_id):
        url = BASEURL.format(ENDPOINTS["stream"].format(game_id))
        return requests.get(url, headers=self.header, stream=True)


    def _get_header(self, token):
        header = {
            "Authorization": "Bearer {}".format(token)
        }

        return header


    def get_profile(self):
        url = BASEURL.format(ENDPOINTS["profile"])
        r = requests.get(url, headers=self.header)
        if r.status_code != 200:
            print("Something went wrong! status_code: {}, response: {}".format(r.status_code, r.text))
            return None

        return r.json()


    def _get_endpoint_url(self, endpoint, args):
        return BASEURL.format(ENDPOINTS[endpoint].format(args))
