"""Imitate `lichess.py`. Used in tests."""
import time
import chess
import chess.engine
import json
from typing import Dict, Union, List, Optional, Generator


class GameStream:
    """Imitate lichess.org's GameStream. Used in tests."""

    def __init__(self) -> None:
        """Initialize `self.moves_sent` to an empty string. It stores the moves that we have already sent."""
        self.moves_sent = ""

    def iter_lines(self) -> Generator[bytes, None, None]:
        """Send the game events to lichess-bot."""
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
                       "wtime": 10000,
                       "btime": 10000,
                       "winc": 100,
                       "binc": 100,
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
            wtime_int, wtime_int = float(wtime), float(btime)
            time.sleep(0.1)
            new_game_state = {"type": "gameState",
                              "moves": moves,
                              "wtime": int(wtime_int * 1000),
                              "btime": int(wtime_int * 1000),
                              "winc": 100,
                              "binc": 100}
            if event == "end":
                new_game_state["status"] = "outoftime"
                new_game_state["winner"] = "black"
                yield json.dumps(new_game_state).encode("utf-8")
                break
            if moves:
                new_game_state["status"] = "started"
                yield json.dumps(new_game_state).encode("utf-8")


class EventStream:
    """Imitate lichess.org's EventStream. Used in tests."""

    def __init__(self, sent_game: bool = False) -> None:
        """:param sent_game: If we have already sent the `gameStart` event, so we don't send it again."""
        self.sent_game = sent_game

    def iter_lines(self) -> Generator[bytes, None, None]:
        """Send the events to lichess-bot."""
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


# Docs: https://lichess.org/api.
class Lichess:
    """Imitate communication with lichess.org."""

    def __init__(self, token: str, url: str, version: str) -> None:
        """Has the same parameters as `lichess.Lichess` to be able to be used in its placed without any modification."""
        self.baseUrl = url
        self.game_accepted = False
        self.moves: List[chess.engine.PlayResult] = []
        self.sent_game = False

    def upgrade_to_bot_account(self) -> None:
        """Isn't used in tests."""
        return

    def make_move(self, game_id: str, move: chess.engine.PlayResult) -> None:
        """Write a move to `./logs/states.txt`, to be read by the opponent."""
        self.moves.append(move)
        uci_move = move.move.uci() if move.move else "error"
        with open("./logs/states.txt") as file:
            contents = file.read().split("\n")
        contents[0] += f" {uci_move}"
        with open("./logs/states.txt", "w") as file:
            file.write("\n".join(contents))

    def chat(self, game_id: str, room: str, text: str) -> None:
        """Isn't used in tests."""
        return

    def abort(self, game_id: str) -> None:
        """Isn't used in tests."""
        return

    def get_event_stream(self) -> EventStream:
        """Send the `EventStream`."""
        events = EventStream(self.sent_game)
        self.sent_game = True
        return events

    def get_game_stream(self, game_id: str) -> GameStream:
        """Send the `GameStream`."""
        return GameStream()

    def accept_challenge(self, challenge_id: str) -> None:
        """Set `self.game_accepted` to true."""
        self.game_accepted = True

    def decline_challenge(self, challenge_id: str, reason: str = "generic") -> None:
        """Isn't used in tests."""
        return

    def get_profile(self) -> Dict[str, Union[str, bool, Dict[str, str]]]:
        """Return a simple profile for the bot that lichess-bot uses when testing."""
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

    def get_ongoing_games(self) -> List[str]:
        """Return that the bot isn't playing a game."""
        return []

    def resign(self, game_id: str) -> None:
        """Isn't used in tests."""
        return

    def get_game_pgn(self, game_id: str) -> str:
        """Return a simple PGN."""
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

    def get_online_bots(self) -> List[Dict[str, Union[str, bool]]]:
        """Return that the only bot online is us."""
        return [{"username": "b", "online": True}]

    def challenge(self, username: str, params: Dict[str, str]) -> None:
        """Isn't used in tests."""
        return

    def cancel(self, challenge_id: str) -> None:
        """Isn't used in tests."""
        return

    def online_book_get(self, path: str, params: Optional[Dict[str, str]] = None) -> None:
        """Isn't used in tests."""
        return

    def is_online(self, user_id: str) -> bool:
        """Return that a bot is online."""
        return True
