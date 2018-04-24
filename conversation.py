import random

LINKS = {
    "LCzero": "http://lczero.org/",
    "Lichess Bots": "https://lichess.org/api#tag/Chess-Bot"
}

class Conversation():
    def __init__(self, game, engine, xhr, version):
        self.game = game
        self.engine = engine
        self.xhr = xhr
        self.version = version

    command_prefix = "!"

    def react(self, line, game):
        print("*** {} [{}] {}: {}".format(self.game.url(), line.room, line.username, line.text.encode("utf-8")))
        if (line.text[0] == self.command_prefix):
            self.command(line, game, line.text[1:].lower())
        pass

    def command(self, line, game, cmd):
        if cmd == "wait" and game.is_abortable():
            game.abort_in(60)
            self.send_reply(line, "Waiting 60 seconds...")
        if cmd == "name" or cmd == "engine" or cmd == "version":
            self.send_reply(line, "{} ID 179".format(self.engine.name()))
        if cmd == "howto":
            self.send_reply(line, "How to run your own bot: lichess.org/api#tag/Chess-Bot")
        if cmd == "commands" or cmd == "help":
            msg = "Supported commands: !name, !eval, !id, !leela, !hardware, !info, and !howto"
            self.send_reply(line, msg)
        if cmd == "eval" or cmd == "stats":
            stats = self.engine.get_stats(True)
            self.send_reply(line, ", ".join(stats))
        if cmd == "id" or cmd == "network":
            self.send_reply(line, "ID 179")
        if cmd.lower() == "elsie" or cmd.lower() == "leela" or cmd.lower() == "leelachess":
            responses = ["Stop it. Let me focus!", "Yes?", "Like what you see? Help me improve at: {}".format(LINKS["LCzero"])]
            self.send_reply(line, random.choice(responses))
        if cmd == "info" or cmd == "links":
            for name, url in LINKS.items():
                self.send_reply(line, "{}: {}".format(name, url))
        if cmd == "hardware" or cmd == "gpu":
            self.send_reply(line, "Running on GTX 1060 6GB, i5-6600K @ 3.50 GHz, 16 GB RAM, Windows 10 Pro")
        if cmd == "queue" or cmd == "challengers":
            self.send_reply(line, "")

    def send_reply(self, line, reply):
        self.xhr.chat(self.game.id, line.room, reply)


class ChatLine():
    def __init__(self, json):
        self.room = json.get("room")
        self.username = json.get("username")
        self.text = json.get("text")
