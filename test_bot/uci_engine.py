"""An engine mimics a UCI engine."""

import chess
from test_games import scholars_mate

assert input() == "uci"


def send_command(command: str) -> None:
    """Send UCI commands to lichess-bot without output buffering."""
    print(command, flush=True)  # noqa: T201 (print() found)


send_command("id name UCI_Test_Bot")
send_command("id author lichess-bot-devs")
send_command("uciok")

board = chess.Board()
while True:
    command, *remaining = input().split()
    if command == "quit":
        break
    elif command == "isready":
        send_command("readyok")
    elif command == "position":
        spec_type, *remaining = remaining
        assert spec_type == "startpos"
        board = chess.Board()
        if remaining:
            moves_label, *move_list = remaining
            assert moves_label == "moves"
            for move in move_list:
                board.push_uci(move)
    elif command == "go":
        move_count = len(board.move_stack)
        move = scholars_mate[move_count]
        send_command(f"bestmove {move}")
