import time
import chess
import json


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
        self.baseUrl = url
        self.game_accepted = False
        self.moves = []
        self.sent_game = False

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
        return {"id": "b",
                "username": "b",
                "online": True,
                "title": "BOT",
                "url": "https://lichess.org/@/b",
                "followable": True,
                "following": False,
                "blocking": False,
                "followsYou": False,
                "perfs": {}}

    def get_ongoing_games(self):
        return []

    def resign(self, game_id):
        return

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
        return

    def reset_connection(self):
        return
