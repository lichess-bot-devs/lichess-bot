"""Allows lichess-bot to send messages to the chat."""
from __future__ import annotations
import logging
import model
from engine_wrapper import EngineWrapper
from lichess import Lichess
from collections.abc import Sequence
MULTIPROCESSING_LIST_TYPE = Sequence[model.Challenge]

logger = logging.getLogger(__name__)


class Conversation:
    """Enables the bot to communicate with its opponent and the spectators."""

    def __init__(self, game: model.Game, engine: EngineWrapper, xhr: Lichess, version: str,
                 challenge_queue: MULTIPROCESSING_LIST_TYPE) -> None:
        """
        Communication between lichess-bot and the game chats.

        :param game: The game that the bot will send messages to.
        :param engine: The engine playing the game.
        :param xhr: A class that is used for communication with lichess.
        :param version: The lichess-bot version.
        :param challenge_queue: The active challenges the bot has.
        """
        self.game = game
        self.engine = engine
        self.xhr = xhr
        self.version = version
        self.challengers = challenge_queue

    command_prefix = "!"

    def react(self, line: ChatLine, game: model.Game) -> None:
        """
        React to a received message.

        :param line: Information about the message.
        :param game: The game that the command came from.
        """
        logger.info(f'*** {self.game.url()} [{line.room}] {line.username}: {line.text.encode("utf-8")!r}')
        if line.text[0] == self.command_prefix:
            self.command(line, game, line.text[1:].lower())

    def command(self, line: ChatLine, game: model.Game, cmd: str) -> None:
        """
        Reacts to the specific commands in the chat.

        :param line: Information about the message.
        :param game: The game that the command came from.
        :param cmd: The command to react to.
        """
        from_self = line.username == self.game.username
        if cmd == "commands" or cmd == "help":
            self.send_reply(line, "Supported commands: !wait (wait a minute for my first move), !name, !howto, !eval, !queue")
        elif cmd == "wait" and game.is_abortable():
            game.ping(60, 120, 120)
            self.send_reply(line, "Waiting 60 seconds...")
        elif cmd == "name":
            name = game.me.name
            self.send_reply(line, f"{name} running {self.engine.name()} (lichess-bot v{self.version})")
        elif cmd == "howto":
            self.send_reply(line, "How to run: Check out 'Lichess Bot API'")
        elif cmd == "eval" and (from_self or line.room == "spectator"):
            stats = self.engine.get_stats(for_chat=True)
            self.send_reply(line, ", ".join(stats))
        elif cmd == "eval":
            self.send_reply(line, "I don't tell that to my opponent, sorry.")
        elif cmd == "queue":
            if self.challengers:
                challengers = ", ".join([f"@{challenger.challenger.name}" for challenger in reversed(self.challengers)])
                self.send_reply(line, f"Challenge queue: {challengers}")
            else:
                self.send_reply(line, "No challenges queued.")

    def send_reply(self, line: ChatLine, reply: str) -> None:
        """
        Send the reply to the chat.

        :param line: Information about the original message that we reply to.
        :param reply: The reply to send.
        """
        logger.info(f'*** {self.game.url()} [{line.room}] {self.game.username}: {reply}')
        self.xhr.chat(self.game.id, line.room, reply)

    def send_message(self, room: str, message: str) -> None:
        """Send the message to the chat."""
        if message:
            self.send_reply(ChatLine({"room": room, "username": "", "text": ""}), message)


class ChatLine:
    """Information about the message."""

    def __init__(self, message_info: dict[str, str]) -> None:
        """Information about the message."""
        self.room = message_info["room"]
        """Whether the message was sent in the chat room or in the spectator room."""
        self.username = message_info["username"]
        """The username of the account that sent the message."""
        self.text = message_info["text"]
        """The message sent."""
