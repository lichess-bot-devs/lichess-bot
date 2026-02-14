"""
StonksfishCrew engine -- a homemade lichess-bot engine that delegates
positional thinking to a crewai-rust ChessThinkTank service and falls
back to the local stonksfish UCI engine (or, as a last resort, a random
legal move) when the service is unavailable.
"""
import chess
import chess.engine
from chess.engine import PlayResult, Limit
import random
import requests
import logging
import os
from lib.engine_wrapper import MinimalEngine
from lib.lichess_types import MOVE, HOMEMADE_ARGS_TYPE

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration -- override via environment variables when needed.
# ---------------------------------------------------------------------------
CREW_SERVICE_URL: str = os.environ.get(
    "CREW_SERVICE_URL",
    "http://localhost:8080/api/v1/chess/think",
)
CREW_SERVICE_TIMEOUT: float = float(os.environ.get("CREW_SERVICE_TIMEOUT", "30"))

STONKSFISH_PATH: str = os.environ.get(
    "STONKSFISH_PATH",
    os.path.join(os.path.dirname(__file__), "..", "engines", "stonksfish"),
)


# ---------------------------------------------------------------------------
# Helper: call the crewai-rust ChessThinkTank service
# ---------------------------------------------------------------------------
def _ask_crew(fen: str, time_limit: Limit | None = None) -> str | None:
    """
    POST the current FEN to the ChessThinkTank crew service and return the
    best-move UCI string, or *None* if the service cannot be reached or
    returns an invalid response.
    """
    payload: dict = {"fen": fen}
    if time_limit is not None:
        if time_limit.time is not None:
            payload["time_limit_seconds"] = time_limit.time
        if time_limit.depth is not None:
            payload["depth"] = time_limit.depth

    try:
        response = requests.post(
            CREW_SERVICE_URL,
            json=payload,
            timeout=CREW_SERVICE_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()

        # The service may return the move under different keys depending
        # on its version.  Try the most likely ones.
        best_move: str | None = (
            data.get("best_move")
            or data.get("bestMove")
            or data.get("move")
        )

        if best_move:
            logger.info(
                "CrewAI ChessThinkTank returned move %s for FEN %s",
                best_move,
                fen,
            )
            return best_move

        logger.warning(
            "CrewAI response did not contain a move field: %s", data
        )
        return None

    except requests.ConnectionError:
        logger.warning(
            "CrewAI ChessThinkTank is not reachable at %s", CREW_SERVICE_URL
        )
    except requests.Timeout:
        logger.warning(
            "CrewAI ChessThinkTank timed out after %.1fs", CREW_SERVICE_TIMEOUT
        )
    except requests.HTTPError as exc:
        logger.warning("CrewAI ChessThinkTank HTTP error: %s", exc)
    except (ValueError, KeyError) as exc:
        logger.warning("Failed to parse CrewAI response: %s", exc)

    return None


# ---------------------------------------------------------------------------
# Helper: fall back to the local stonksfish UCI engine
# ---------------------------------------------------------------------------
def _ask_stonksfish(
    board: chess.Board,
    time_limit: Limit,
) -> PlayResult | None:
    """
    Run the local stonksfish UCI engine and return its best move, or *None*
    if the engine binary is missing or errors out.
    """
    engine_path = os.path.abspath(STONKSFISH_PATH)
    if not os.path.isfile(engine_path):
        logger.warning("Stonksfish binary not found at %s", engine_path)
        return None

    try:
        engine = chess.engine.SimpleEngine.popen_uci(engine_path, timeout=10)
        try:
            result = engine.play(board, time_limit, info=chess.engine.INFO_ALL)
            logger.info(
                "Stonksfish UCI engine returned move %s", result.move
            )
            return result
        finally:
            engine.quit()
    except Exception as exc:
        logger.warning("Stonksfish UCI engine failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# The engine class exposed to lichess-bot
# ---------------------------------------------------------------------------
class StonksfishCrewEngine(MinimalEngine):
    """
    Homemade engine that queries the crewai-rust ChessThinkTank for the
    best move.  If the crew service is unavailable it falls back -- first
    to the local stonksfish UCI engine, then to a random legal move.
    """

    def search(
        self,
        board: chess.Board,
        time_limit: Limit,
        ponder: bool,
        draw_offered: bool,
        root_moves: MOVE,
    ) -> PlayResult:
        """
        Choose a move by consulting, in order:

        1. The crewai-rust ChessThinkTank HTTP service.
        2. The local stonksfish UCI engine.
        3. A random legal move (ultimate fallback).
        """
        fen = board.fen()
        possible_moves = (
            root_moves if isinstance(root_moves, list) else list(board.legal_moves)
        )

        # --- 1. Try the CrewAI ChessThinkTank service ----------------------
        crew_uci = _ask_crew(fen, time_limit)
        if crew_uci is not None:
            try:
                move = chess.Move.from_uci(crew_uci)
                if move in possible_moves:
                    return PlayResult(
                        move,
                        None,
                        {"string": "lichess-bot-source:CrewAI ChessThinkTank"},
                        draw_offered=draw_offered,
                    )
                logger.warning(
                    "CrewAI returned illegal move %s; falling back.", crew_uci
                )
            except (ValueError, chess.InvalidMoveError) as exc:
                logger.warning(
                    "CrewAI returned unparseable move '%s': %s; falling back.",
                    crew_uci,
                    exc,
                )

        # --- 2. Try the local stonksfish UCI engine -------------------------
        sf_result = _ask_stonksfish(board, time_limit)
        if sf_result is not None and sf_result.move is not None:
            if sf_result.move in possible_moves:
                sf_result.draw_offered = draw_offered
                if sf_result.info:
                    sf_result.info["string"] = "lichess-bot-source:Stonksfish UCI"
                else:
                    sf_result.info = {"string": "lichess-bot-source:Stonksfish UCI"}
                return sf_result
            logger.warning(
                "Stonksfish returned move %s not in root_moves; falling back.",
                sf_result.move,
            )

        # --- 3. Ultimate fallback: random legal move ------------------------
        logger.warning("All engines unavailable; choosing a random legal move.")
        move = random.choice(possible_moves)
        return PlayResult(
            move,
            None,
            {"string": "lichess-bot-source:Random Fallback"},
            draw_offered=draw_offered,
        )
