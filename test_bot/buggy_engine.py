"""An engine that takes too much time to make a move during tests."""

import chess
import time

assert input() == "uci"


def send_command(command: str) -> None:
    """Send UCI commands to lichess-bot without output buffering."""
    print(command, flush=True)  # noqa: T201 (print() found)


send_command("id name Procrastinator")
send_command("id author MZH")
send_command("uciok")

delay_performed = False
just_started = True
scholars_mate = ["a2a3", "e7e5", "a3a4", "f8c5", "a4a5", "d8h4", "a5a6", "h4f2"]

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
        if just_started and len(board.move_stack) > 1:
            delay_performed = True
    elif command == "go":
        move_count = len(board.move_stack)
        if move_count == 3 and not delay_performed:
            send_command("info string delaying move")
            delay_performed = True
            time.sleep(11)
        move = scholars_mate[move_count]
        send_command(f"bestmove {move}")
        just_started = False
