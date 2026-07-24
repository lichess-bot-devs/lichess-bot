"""Prompt templates and response parsing for LLM move selection."""
from __future__ import annotations

import re

import chess

DEFAULT_SYSTEM_PROMPT = (
    "You are a chess engine. You must reply with exactly one legal move in UCI format "
    "(e.g. e2e4, g1f3, e7e8q for promotion). Do not include explanations, punctuation, "
    "or any text other than the move."
)

UCI_PATTERN = re.compile(r"\b([a-h][1-8][a-h][1-8][qrbn]?)\b", re.IGNORECASE)


def format_move_history(board: chess.Board) -> str:
    """Return the game move list in SAN notation."""
    if not board.move_stack:
        return "(no moves yet)"
    temp = chess.Board(board.fen())
    sans: list[str] = []
    for move in board.move_stack:
        sans.append(temp.san(move))
        temp.push(move)
    return " ".join(sans)


def format_legal_moves(board: chess.Board) -> str:
    """Return legal moves as a numbered UCI list."""
    moves = sorted(str(move) for move in board.legal_moves)
    return "\n".join(f"{index + 1}. {move}" for index, move in enumerate(moves))


def build_move_prompt(board: chess.Board) -> str:
    """Build the user prompt for the current position."""
    side = "White" if board.turn == chess.WHITE else "Black"
    return (
        f"FEN: {board.fen()}\n"
        f"Side to move: {side}\n"
        f"Move history (SAN): {format_move_history(board)}\n"
        f"Legal moves (UCI):\n{format_legal_moves(board)}\n"
        "Reply with one legal UCI move only."
    )


def build_retry_prompt(error: str, board: chess.Board) -> str:
    """Build a correction prompt after an invalid LLM response."""
    return (
        f"Your previous reply was invalid: {error}\n"
        f"Legal moves (UCI):\n{format_legal_moves(board)}\n"
        "Reply with one legal UCI move only."
    )


def parse_uci_move(response: str, board: chess.Board) -> chess.Move:
    """
    Parse a UCI move from an LLM response and validate it against the board.

    :raises ValueError: If no valid legal move can be parsed.
    """
    cleaned = response.strip().strip("\"'`")
    if not cleaned:
        raise ValueError("empty response")

    candidate = cleaned.lower()
    match = UCI_PATTERN.search(candidate)
    if match:
        candidate = match.group(1).lower()

    try:
        move = board.parse_uci(candidate)
    except ValueError as error:
        raise ValueError(f"could not parse UCI move from {response!r}") from error

    if move not in board.legal_moves:
        raise ValueError(f"{candidate} is not a legal move in this position")

    return move
