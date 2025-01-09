"""Tests for the models."""

import datetime
from lib import model
import yaml
from lib import config
from collections import defaultdict, Counter
from lib.timer import Timer
from lib.lichess_types import ChallengeType, UserProfileType, GameEventType, PlayerType


def test_challenge() -> None:
    """Test the challenge model."""
    challenge: ChallengeType = {"id": "zzzzzzzz", "url": "https://lichess.org/zzzzzzzz", "status": "created",
                                "challenger": {"id": "c", "name": "c", "rating": 2000, "title": None, "online": True},
                                "destUser": {"id": "b", "name": "b", "rating": 3000, "title": "BOT", "online": True},
                                "variant": {"key": "standard", "name": "Standard", "short": "Std"}, "rated": False,
                                "speed": "bullet",
                                "timeControl": {"type": "clock", "limit": 90, "increment": 1, "show": "1.5+1"},
                                "color": "random", "finalColor": "white", "perf": {"icon": "\ue032", "name": "Bullet"}}
    user_profile: UserProfileType = {"id": "b", "username": "b",
                                     "perfs": {"bullet": {"games": 100, "rating": 3000, "rd": 150, "prog": -10},
                                               "blitz": {"games": 100, "rating": 3000, "rd": 150, "prog": -10},
                                               "rapid": {"games": 100, "rating": 3000, "rd": 150, "prog": -10},
                                               "classical": {"games": 100, "rating": 3000, "rd": 150, "prog": -10},
                                               "correspondence": {"games": 100, "rating": 3000, "rd": 150, "prog": -10},
                                               "antichess": {"games": 100, "rating": 3000, "rd": 150, "prog": -10,
                                                             "prov": True}},
                                     "title": "BOT", "createdAt": 1500000000000,
                                     "profile": {"bio": "This is my bio",
                                                 "links": "https://github.com/lichess-bot-devs/lichess-bot"},
                                     "seenAt": 1700000000000, "playTime": {"total": 1000000, "tv": 10000},
                                     "url": "https://lichess.org/@/b",
                                     "count": {"all": 600, "rated": 500, "ai": 50, "draw": 200, "drawH": 50, "loss": 50,
                                               "lossH": 50, "win": 250, "winH": 200, "bookmark": 0, "playing": 0,
                                               "import": 0, "me": 0},
                                     "followable": True, "following": False, "blocking": False}

    with open("./config.yml.default") as file:
        CONFIG = yaml.safe_load(file)
    CONFIG["token"] = ""
    CONFIG["challenge"]["allow_list"] = []
    CONFIG["challenge"]["block_list"] = []
    configuration = config.Configuration(CONFIG).challenge
    recent_challenges: defaultdict[str, list[Timer]] = defaultdict()
    recent_challenges["c"] = []

    challenge_model = model.Challenge(challenge, user_profile)
    assert challenge_model.id == "zzzzzzzz"
    assert challenge_model.rated is False
    assert challenge_model.variant == "standard"
    assert challenge_model.speed == "bullet"
    assert challenge_model.time_control["show"] == "1.5+1"
    assert challenge_model.color == "white"
    assert challenge_model.is_supported(configuration, recent_challenges, Counter()) == (True, "")

    CONFIG["challenge"]["min_base"] = 120
    assert challenge_model.is_supported(configuration, recent_challenges, Counter()) == (False, "timeControl")


def test_game() -> None:
    """Test the game model."""
    game: GameEventType = {"id": "zzzzzzzz", "variant": {"key": "standard", "name": "Standard", "short": "Std"},
                           "speed": "bullet", "perf": {"name": "Bullet"}, "rated": False, "createdAt": 1700000000000,
                           "white": {"id": "c", "name": "c", "title": None, "rating": 2000},
                           "black": {"id": "b", "name": "b", "title": "BOT", "rating": 3000},
                           "initialFen": "startpos", "clock": {"initial": 90000, "increment": 1000}, "type": "gameFull",
                           "state": {"type": "gameState", "moves": "", "wtime": 90000, "btime": 90000, "winc": 1000,
                                     "binc": 1000, "status": "started"}}
    username = "b"
    base_url = "https://lichess.org/"
    abort_time = datetime.timedelta(seconds=30)

    game_model = model.Game(game, username, base_url, abort_time)
    assert game_model.id == "zzzzzzzz"
    assert game_model.mode == "casual"
    assert game_model.is_white is False


def test_player() -> None:
    """Test the player model."""
    player: PlayerType = {"id": "b", "name": "b", "rating": 3000, "title": "BOT", "online": True}
    player_model = model.Player(player)
    assert player_model.is_bot is True
    assert str(player_model) == "BOT b (3000)"
