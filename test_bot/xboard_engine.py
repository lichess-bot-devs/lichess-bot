"""An engine mimics an XBoard engine."""

import chess
import typing

if typing.TYPE_CHECKING:
    from test_bot.test_games import scholars_mate
else:
    from test_games import scholars_mate

assert input() == "xboard"
assert input() == "protover 2"


def send_command(command: str) -> None:
    """Send UCI commands to lichess-bot without output buffering."""
    print(command, flush=True)  # noqa: T201 (print() found)


send_command('feature myname="XBoard Test Bot" ping=1 setboard=1 usermove=1 done=1')

board = chess.Board()
while True:
    command, *remaining = input().split()
    if command == "quit":
        break
    elif command == "ping":
        send_command(f"pong {''.join(remaining)}")
    elif command == "new":
        board = chess.Board()
    elif command == "usermove":
        board.push_xboard("".join(remaining))
        move_count = len(board.move_stack)
        move = scholars_mate[move_count]
        send_command(f"move {move}")
        board.push_xboard(move)
