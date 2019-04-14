import time
import chess

from chess.variant import find_variant
from urllib.parse import urljoin

from src.constants import TEN_YEARS_IN_MS, MAX_ABORT_MOVES, MIN_FAKE_THINK_MOVES
from src.models.player import Player
import logging


class Game:
    def __init__(self, json, username, base_url, abort_time, fake_think_time):
        self.username = username
        self.id = json.get("id")
        self.white = Player(json.get("white"))
        self.black = Player(json.get("black"))

        self.speed = json.get("speed")
        clock = json.get("clock", {}) or {}
        self.clock_initial = clock.get("initial", TEN_YEARS_IN_MS)
        self.clock_increment = clock.get("increment", 0)

        self.perf_name = json.get("perf").get("name") if json.get("perf") else "{perf?}"
        self.variant_name = json.get("variant")["name"]
        self.initial_fen = json.get("initialFen")
        self.state = json.get("state")
        self.is_white = bool(self.white.name and self.white.name == username)
        self.base_url = base_url
        self.white_starts = self.initial_fen == "startpos" or self.initial_fen.split()[1] == "w"
        self.abort_time = abort_time
        self.abort_at = time.time() + abort_time

        self.board = None
        self.setup_board()

        self.fake_think_enabled = fake_think_time

    def get_board(self):
        return self.board

    def me(self):
        return self.white if self.is_white else self.black

    def opponent(self):
        return self.black if self.is_white else self.white

    def my_color(self):
        return "white" if self.is_white else "black"

    def opponent_color(self):
        return "black" if self.is_white else "white"

    def url(self):
        return urljoin(self.base_url, "{}/{}".format(self.id, self.my_color()))

    def is_abortable(self):
        return len(self.state["moves"]) < MAX_ABORT_MOVES

    def update_abort_time(self):
        if self.is_abortable():
            self.abort_at = time.time() + self.abort_time

    def should_abort_now(self):
        return self.is_abortable() and time.time() > self.abort_at

    def my_remaining_seconds(self):
        return (self.state["wtime"] if self.is_white else self.state["btime"]) / 1000

    def update_board(self, move):
        self.board.push(chess.Move.from_uci(move))

    def is_white_to_move(self):
        return self.board.turn

    def is_my_move(self):
        return self.is_white == self.is_white_to_move()

    def setup_board(self):

        if self.variant_name.lower() == "chess960":
            self.board = chess.Board(self.initial_fen, chess960=True)
        elif self.variant_name == "From Position":
            self.board = chess.Board(self.initial_fen)
        else:
            VariantBoard = find_variant(self.variant_name)
            self.board = VariantBoard()

        moves = self.state["moves"].split()
        for move in moves:
            self.update_board(move)

    def fake_think(self):
        moves = self.board.fullmove_number

        if self.fake_think_enabled and self.is_my_move() and moves > MIN_FAKE_THINK_MOVES:
            delay = min(self.clock_initial, self.my_remaining_seconds()) * 0.015
            accel = 1 - max(0, min(100, len(moves) - 20)) / 150
            sleep = min(5, delay * accel)
            time.sleep(sleep)

    def get_pretty_name(self):
        return "{} {} vs {}".format(self.url(), self.perf_name, self.opponent().name)