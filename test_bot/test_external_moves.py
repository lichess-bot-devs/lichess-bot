"""Test the functions that get the external moves."""
import backoff
import requests
import yaml
import os
import chess
import logging
import chess.engine
from datetime import timedelta
from copy import deepcopy
from requests.exceptions import ConnectionError as RequestsConnectionError, HTTPError, ReadTimeout, RequestException
from http.client import RemoteDisconnected
from lib.lichess_types import OnlineType, GameEventType
from typing import Optional, Union, cast
from lib.lichess import is_final, backoff_handler, Lichess
from lib.config import Configuration, insert_default_values
from lib.model import Game
from lib.engine_wrapper import get_online_move, get_book_move


class MockLichess(Lichess):
    """A modified Lichess class for communication with external move sources."""

    def __init__(self) -> None:
        """Initialize only self.other_session and not self.session."""
        self.max_retries = 3
        self.other_session = requests.Session()

    def online_book_get(self, path: str, params: Optional[dict[str, Union[str, int]]] = None,
                        stream: bool = False) -> OnlineType:
        """Get an external move from online sources (chessdb or lichess.org)."""

        @backoff.on_exception(backoff.constant,
                              (RemoteDisconnected, RequestsConnectionError, HTTPError, ReadTimeout),
                              max_time=60,
                              max_tries=self.max_retries,
                              interval=0.1,
                              giveup=is_final,
                              on_backoff=backoff_handler,
                              backoff_log_level=logging.DEBUG,
                              giveup_log_level=logging.DEBUG)
        def online_book_get() -> OnlineType:
            json_response: OnlineType = self.other_session.get(path, timeout=2, params=params, stream=stream).json()
            return json_response

        return online_book_get()

    def is_website_up(self, url: str) -> bool:
        """Check if a website is up."""
        try:
            self.other_session.get(url, timeout=2)
            return True
        except RequestException:
            return False


def get_configs() -> tuple[Configuration, Configuration, Configuration, Configuration]:
    """Create the configs used for the tests."""
    with open("./config.yml.default") as file:
        CONFIG = yaml.safe_load(file)
    insert_default_values(CONFIG)
    CONFIG["engine"]["online_moves"]["lichess_cloud_analysis"]["enabled"] = True
    CONFIG["engine"]["online_moves"]["online_egtb"]["enabled"] = True
    CONFIG["engine"]["draw_or_resign"]["resign_enabled"] = True
    CONFIG["engine"]["polyglot"]["enabled"] = True
    CONFIG["engine"]["polyglot"]["book"]["standard"] = ["TEMP/gm2001.bin"]
    engine_cfg = Configuration(CONFIG).engine
    CONFIG_2 = deepcopy(CONFIG)
    CONFIG_2["engine"]["online_moves"]["chessdb_book"]["enabled"] = True
    CONFIG_2["engine"]["online_moves"]["online_egtb"]["source"] = "chessdb"
    engine_cfg_2 = Configuration(CONFIG_2).engine
    return engine_cfg.online_moves, engine_cfg_2.online_moves, engine_cfg.draw_or_resign, engine_cfg.polyglot


def get_game() -> Game:
    """Create a model.Game to be used in the tests."""
    game_event: GameEventType = {"id": "zzzzzzzz",
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
                                           "wtime": 1000000,
                                           "btime": 1000000,
                                           "winc": 2000,
                                           "binc": 2000,
                                           "status": "started"}}
    return Game(game_event, "b", "https://lichess.org", timedelta(seconds=60))


def download_opening_book() -> None:
    """Download gm2001.bin."""
    if os.path.exists("./TEMP/gm2001.bin"):
        return
    response = requests.get("https://github.com/gmcheems-org/free-opening-books/raw/main/books/bin/gm2001.bin",
                            allow_redirects=True)
    with open("./TEMP/gm2001.bin", "wb") as file:
        file.write(response.content)


os.makedirs("TEMP", exist_ok=True)


def get_online_move_wrapper(li: Lichess, board: chess.Board, game: Game, online_moves_cfg: Configuration,
                            draw_or_resign_cfg: Configuration) -> chess.engine.PlayResult:
    """Wrap `lib.engine_wrapper.get_online_move` so that it only returns a PlayResult type."""
    return cast(chess.engine.PlayResult, get_online_move(li, board, game, online_moves_cfg, draw_or_resign_cfg))


def test_external_moves() -> None:
    """Test that the code for external moves works properly."""
    li = MockLichess()
    game = get_game()
    download_opening_book()
    online_cfg, online_cfg_2, draw_or_resign_cfg, polyglot_cfg = get_configs()

    starting_fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    opening_fen = "rn1q1rk1/pbp1bpp1/1p2pn1p/3p4/2PP3B/2N1PN2/PP2BPPP/R2QK2R w KQ - 2 9"
    middlegame_fen = "8/5p2/1n1p1nk1/1p1Pp1p1/1Pp1P1Pp/r1P2B1P/2RNKP2/8 w - - 0 31"
    endgame_wdl2_fen = "2k5/4n2Q/5N2/8/8/8/1r6/2K5 b - - 0 123"
    endgame_wdl1_fen = "6N1/3n4/3k1b2/8/8/7Q/1r6/5K2 b - - 6 9"
    endgame_wdl0_fen = "6N1/3n4/3k1b2/8/8/7Q/5K2/1r6 b - - 8 10"

    is_lichess_org_up = li.is_website_up("https://lichess.org/api/cloud-eval")
    is_lichess_ovh_up = li.is_website_up("https://tablebase.lichess.ovh/standard")
    is_chessdb_cn_up = li.is_website_up("https://www.chessdb.cn/cdb.php")

    # Test lichess_cloud_analysis.
    if is_lichess_org_up:
        assert get_online_move_wrapper(li, chess.Board(starting_fen), game, online_cfg, draw_or_resign_cfg).move is not None
        assert get_online_move_wrapper(li, chess.Board(opening_fen), game, online_cfg, draw_or_resign_cfg).move is not None
        assert get_online_move_wrapper(li, chess.Board(middlegame_fen), game, online_cfg, draw_or_resign_cfg).move is None

    # Test chessdb_book.
    if is_chessdb_cn_up:
        assert get_online_move_wrapper(li, chess.Board(starting_fen), game, online_cfg_2, draw_or_resign_cfg).move is not None
        assert get_online_move_wrapper(li, chess.Board(opening_fen), game, online_cfg_2, draw_or_resign_cfg).move is not None
        assert get_online_move_wrapper(li, chess.Board(middlegame_fen), game, online_cfg_2, draw_or_resign_cfg).move is None

    # Test online_egtb with lichess.
    if is_lichess_ovh_up:
        assert get_online_move_wrapper(li, chess.Board(endgame_wdl2_fen), game, online_cfg, draw_or_resign_cfg).resigned
        assert get_online_move_wrapper(li, chess.Board(endgame_wdl0_fen), game, online_cfg, draw_or_resign_cfg).draw_offered
        wdl1_move = get_online_move_wrapper(li, chess.Board(endgame_wdl1_fen), game, online_cfg, draw_or_resign_cfg)
        assert not wdl1_move.resigned and not wdl1_move.draw_offered
        # Test with reversed colors.
        assert get_online_move_wrapper(li, chess.Board(endgame_wdl2_fen).mirror(), game, online_cfg,
                                       draw_or_resign_cfg).resigned
        assert get_online_move_wrapper(li, chess.Board(endgame_wdl0_fen).mirror(), game, online_cfg,
                                       draw_or_resign_cfg).draw_offered
        wdl1_move = get_online_move_wrapper(li, chess.Board(endgame_wdl1_fen).mirror(), game, online_cfg, draw_or_resign_cfg)
        assert not wdl1_move.resigned and not wdl1_move.draw_offered

    # Test online_egtb with chessdb.
    if is_chessdb_cn_up:
        assert get_online_move_wrapper(li, chess.Board(endgame_wdl2_fen), game, online_cfg_2, draw_or_resign_cfg).resigned
        assert get_online_move_wrapper(li, chess.Board(endgame_wdl0_fen), game, online_cfg_2, draw_or_resign_cfg).draw_offered
        wdl1_move = get_online_move_wrapper(li, chess.Board(endgame_wdl1_fen), game, online_cfg_2, draw_or_resign_cfg)
        assert not wdl1_move.resigned and not wdl1_move.draw_offered
        # Test with reversed colors.
        assert get_online_move_wrapper(li, chess.Board(endgame_wdl2_fen).mirror(), game, online_cfg_2,
                                       draw_or_resign_cfg).resigned
        assert get_online_move_wrapper(li, chess.Board(endgame_wdl0_fen).mirror(), game, online_cfg_2,
                                       draw_or_resign_cfg).draw_offered
        wdl1_move = get_online_move_wrapper(li, chess.Board(endgame_wdl1_fen).mirror(), game, online_cfg_2, draw_or_resign_cfg)
        assert not wdl1_move.resigned and not wdl1_move.draw_offered

    # Test opening book.
    assert get_book_move(chess.Board(opening_fen), game, polyglot_cfg).move == chess.Move.from_uci("h4f6")
