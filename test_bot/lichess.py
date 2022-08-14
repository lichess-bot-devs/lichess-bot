import logging
import requests
from urllib.parse import urljoin
from requests.exceptions import ConnectionError, HTTPError, ReadTimeout
from http.client import RemoteDisconnected
import backoff
import time
import chess
import json

logger = logging.getLogger(__name__)

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


def rate_limit_check(response):
    if response.status_code == 429:
        logger.warning("Rate limited. Waiting 1 minute until next request.")
        time.sleep(60)
        return True
    return False


class GameStream:
    def __init__(self):
        self.moves_sent = ""

    def iter_lines(self):
        yield json.dumps(
            {"id": "zzzzzzzz",
             "variant": {"key": "standard",
                         "name": "Standard",
                         "short": "Std"},
             "clock": {"initial": 60000,
                       "increment": 2000},
             "speed": "bullet",
             "perf": {"name": "Bullet"},
             "rated": True,
             "createdAt": 1600000000000,
             "white": {"id": "bo",
                       "name": "bo",
                       "title": "BOT",
                       "rating": 3000},
             "black": {"id": "b",
                       "name": "b",
                       "title": "BOT",
                       "rating": 3000,
                       "provisional": True},
             "initialFen": "startpos",
             "type": "gameFull",
             "state": {"type": "gameState",
                       "moves": "",
                       "wtime": 60000,
                       "btime": 60000,
                       "winc": 2000,
                       "binc": 2000,
                       "status": "started"}}).encode("utf-8")
        time.sleep(1)
        while True:
            time.sleep(0.001)
            with open("./logs/events.txt") as events:
                event = events.read()
            while True:
                try:
                    with open("./logs/states.txt") as states:
                        state = states.read().split("\n")
                    moves = state[0]
                    board = chess.Board()
                    for move in moves.split():
                        board.push_uci(move)
                    wtime, btime = state[1].split(",")
                    if len(moves) <= len(self.moves_sent) and not event:
                        time.sleep(0.001)
                        continue
                    self.moves_sent = moves
                    break
                except (IndexError, ValueError):
                    pass
            wtime, btime = float(wtime), float(btime)
            time.sleep(0.1)
            new_game_state = {"type": "gameState",
                              "moves": moves,
                              "wtime": int(wtime * 1000),
                              "btime": int(btime * 1000),
                              "winc": 2000,
                              "binc": 2000}
            if event == "end":
                new_game_state["status"] = "outoftime"
                new_game_state["winner"] = "black"
                yield json.dumps(new_game_state).encode("utf-8")
                break
            if moves:
                new_game_state["status"] = "started"
                yield json.dumps(new_game_state).encode("utf-8")


class EventStream:
    def __init__(self, sent_game=False):
        self.sent_game = sent_game

    def iter_lines(self):
        if self.sent_game:
            yield b''
            time.sleep(1)
        else:
            yield json.dumps(
                {"type": "gameStart",
                 "game": {"id": "zzzzzzzz",
                          "source": "friend",
                          "compat": {"bot": True,
                                     "board": True}}}).encode("utf-8")


# docs: https://lichess.org/api
class Lichess:
    def __init__(self, token, url, version):
        self.version = version
        self.header = {
            "Authorization": f"Bearer {token}"
        }
        self.baseUrl = url
        self.session = requests.Session()
        self.session.headers.update(self.header)
        self.set_user_agent("?")
        self.game_accepted = False
        self.moves = []
        self.sent_game = False

    def is_final(exception):
        return isinstance(exception, HTTPError) and exception.response.status_code < 500

    @backoff.on_exception(backoff.constant,
                          (RemoteDisconnected, ConnectionError, HTTPError, ReadTimeout),
                          max_time=60,
                          interval=0.1,
                          giveup=is_final)
    def api_get(self, path, get_raw_text=False):
        logging.getLogger("backoff").setLevel(self.logging_level)
        url = urljoin(self.baseUrl, path)
        response = self.session.get(url, timeout=2)
        rate_limit_check(response)
        response.raise_for_status()
        response.encoding = "utf-8"
        return response.text if get_raw_text else response.json()

    @backoff.on_exception(backoff.constant,
                          (RemoteDisconnected, ConnectionError, HTTPError, ReadTimeout),
                          max_time=60,
                          interval=0.1,
                          giveup=is_final)
    def api_post(self, path, data=None, headers=None, params=None, payload=None, raise_for_status=True):
        logging.getLogger("backoff").setLevel(self.logging_level)
        url = urljoin(self.baseUrl, path)
        response = self.session.post(url, data=data, headers=headers, params=params, json=payload, timeout=2)
        if rate_limit_check(response) or raise_for_status:
            response.raise_for_status()
        return response.json()

    def get_game(self, game_id):
        return

    def upgrade_to_bot_account(self):
        return

    def make_move(self, game_id, move):
        self.moves.append(move)
        uci_move = move.move.uci()
        with open("./logs/states.txt") as file:
            contents = file.read().split("\n")
        contents[0] += f" {uci_move}"
        with open("./logs/states.txt", "w") as file:
            file.write("\n".join(contents))

    def chat(self, game_id, room, text):
        return

    def abort(self, game_id):
        return

    def get_event_stream(self):
        events = EventStream(self.sent_game)
        self.sent_game = True
        return events

    def get_game_stream(self, game_id):
        return GameStream()

    def accept_challenge(self, challenge_id):
        self.game_accepted = True

    def decline_challenge(self, challenge_id, reason="generic"):
        return

    def get_profile(self):
        profile = {"id": "b",
                   "username": "b",
                   "online": True,
                   "title": "BOT",
                   "url": "https://lichess.org/@/b",
                   "followable": True,
                   "following": False,
                   "blocking": False,
                   "followsYou": False,
                   "perfs": {}}
        self.set_user_agent(profile["username"])
        return profile

    def get_ongoing_games(self):
        return []

    def resign(self, game_id):
        return

    def set_user_agent(self, username):
        self.header.update({"User-Agent": f"lichess-bot/{self.version} user:{username}"})
        self.session.headers.update(self.header)

    def get_game_pgn(self, game_id):
        return """
[Event "Test game"]
[Site "pytest"]
[Date "2022.03.11"]
[Round "1"]
[White "Engine"]
[Black "Engine"]
[Result "0-1"]

*
"""

    def get_online_bots(self):
        return [{"username": "b", "online": True}]

    def challenge(self, username, params):
        return

    def cancel(self, challenge_id):
        return

    def online_book_get(self, path, params=None):
        return self.session.get(path, timeout=2, params=params).json()

    def reset_connection(self):
        return
