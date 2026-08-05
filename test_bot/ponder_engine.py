"""An engine that mimics a UCI engine that supports pondering."""

import chess
import typing

if typing.TYPE_CHECKING:
    from test_bot.test_games import scholars_mate
else:
    from test_games import scholars_mate

assert input() == "uci"


def send_command(command: str) -> None:
    """Send UCI commands to lichess-bot without output buffering."""
    print(command, flush=True)  # noqa: T201 (print() found)


def bestmove_command(board: chess.Board) -> str:
    """Choose the next scripted move and predict the opponent's reply for pondering."""
    move_count = len(board.move_stack)
    command = f"bestmove {scholars_mate[move_count]}"
    if move_count + 1 < len(scholars_mate):
        command += f" ponder {scholars_mate[move_count + 1]}"
    return command


send_command("id name UCI_Ponder_Test_Bot")
send_command("id author lichess-bot-devs")
send_command("uciok")

board = chess.Board()
pondering = False
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
        if "ponder" in remaining:
            # Search quietly until "ponderhit" or "stop" arrives.
            pondering = True
        else:
            send_command(bestmove_command(board))
    elif command in ("ponderhit", "stop") and pondering:
        pondering = False
        send_command(bestmove_command(board))
