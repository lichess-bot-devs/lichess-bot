from __future__ import annotations
import logging
import model
from engine_wrapper import EngineWrapper
from lichess import Lichess
from typing import Dict, List
MULTIPROCESSING_LIST_TYPE = List[model.Challenge]

logger = logging.getLogger(__name__)


class Conversation:
    def __init__(self, game: model.Game, engine: EngineWrapper, xhr: Lichess, version: str,
                 challenge_queue: MULTIPROCESSING_LIST_TYPE) -> None:
        self.game = game
        self.engine = engine
        self.xhr = xhr
        self.version = version
        self.challengers = challenge_queue

    command_prefix = "!"

    def react(self, line: ChatLine, game: model.Game) -> None:
        logger.info(f'*** {self.game.url()} [{line.room}] {line.username}: {line.text.encode("utf-8")!r}')
        if line.text[0] == self.command_prefix:
            self.command(line, game, line.text[1:].lower())

    def command(self, line: ChatLine, game: model.Game, cmd: str) -> None:
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
        logger.info(f'*** {self.game.url()} [{line.room}] {self.game.username}: {reply}')
        self.xhr.chat(self.game.id, line.room, reply)

    def send_message(self, room: str, message: str) -> None:
        if message:
            self.send_reply(ChatLine({"room": room, "username": "", "text": ""}), message)


class ChatLine:
    def __init__(self, json: Dict[str, str]) -> None:
        self.room = json["room"]
        self.username = json["username"]
        self.text = json["text"]
