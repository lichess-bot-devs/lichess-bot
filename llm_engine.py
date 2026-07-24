"""Homemade engine that selects moves via an LLM API."""
from __future__ import annotations

import logging

import chess
import chess.engine

from lib.engine_wrapper import MinimalEngine
from lib.config import Configuration
from lib.llm.client import LLMClient, create_client
from lib.llm.prompt import (
    DEFAULT_SYSTEM_PROMPT,
    build_move_prompt,
    build_retry_prompt,
    parse_uci_move,
)
from lib.lichess_types import COMMANDS_TYPE, MOVE, OPTIONS_GO_EGTB_TYPE
from lib import model

logger = logging.getLogger(__name__)


class LLMEngine(MinimalEngine):
    """Select chess moves by calling a configured LLM provider."""

    def __init__(self,
                 commands: COMMANDS_TYPE,
                 options: OPTIONS_GO_EGTB_TYPE,
                 stderr: int | None,  # noqa: ARG002
                 draw_or_resign: Configuration,
                 game: model.Game | None,  # noqa: ARG002
                 debug: bool,  # noqa: ARG002
                 llm_config: Configuration | None = None,
                 client: LLMClient | None = None,
                 **popen_args: str) -> None:  # noqa: ARG002
        """Initialize the LLM engine."""
        super().__init__(commands, options, stderr, draw_or_resign, game, debug)
        self.llm_config = llm_config or Configuration({})
        self._client = client
        self.max_retries = int(self.llm_config.lookup("max_retries") if self.llm_config.lookup("max_retries") is not None else 2)
        self.accept_draw_when_offered = bool(
            self.llm_config.lookup("accept_draw_when_offered")
            if self.llm_config.lookup("accept_draw_when_offered") is not None
            else True
        )
        configured_prompt = self.llm_config.lookup("system_prompt")
        self.system_prompt = configured_prompt if configured_prompt else DEFAULT_SYSTEM_PROMPT

    @property
    def client(self) -> LLMClient:
        """Lazy-load the configured LLM client."""
        if self._client is None:
            self._client = create_client(self.llm_config)
        return self._client

    def name(self) -> str:
        """Return a descriptive engine name for chat commands."""
        provider = self.llm_config.lookup("provider") or "llm"
        model = self.llm_config.lookup("model") or "unknown"
        return f"LLM ({provider}/{model})"

    def search(self,
               board: chess.Board,
               time_limit: chess.engine.Limit,  # noqa: ARG002
               ponder: bool,  # noqa: ARG002
               draw_offered: bool,
               root_moves: MOVE) -> chess.engine.PlayResult:
        """Ask the LLM for a legal move in the current position."""
        if draw_offered and self.accept_draw_when_offered:
            return chess.engine.PlayResult(None, None, draw_offered=True)

        legal_moves = root_moves if isinstance(root_moves, list) else list(board.legal_moves)
        user_prompt = build_move_prompt(board)
        last_error = "no valid response"

        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.complete(self.system_prompt, user_prompt)
                move = parse_uci_move(response, board)
                if legal_moves and move not in legal_moves:
                    raise ValueError(f"{move.uci()} is not among the allowed root moves")
                logger.debug("LLM chose move %s on attempt %s", move.uci(), attempt + 1)
                return chess.engine.PlayResult(move, None)
            except (RuntimeError, ValueError) as error:
                last_error = str(error)
                logger.warning("LLM move attempt %s failed: %s", attempt + 1, last_error)
                if attempt >= self.max_retries:
                    break
                user_prompt = build_retry_prompt(last_error, board)

        raise chess.engine.EngineError(f"LLM failed to produce a legal move after retries: {last_error}")
