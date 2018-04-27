import random

LINKS = {
    "LCzero": "http://lczero.org/",
    "Lichess Bots": "https://lichess.org/api#tag/Chess-Bot"
}

ID = 33
NODES = 1

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
        if cmd == "name":
            self.send_reply(line, "{} ID {}, nodes={} (lichess-bot v{})".format(self.engine.name(), ID, NODES, self.version))
        if cmd == "howto":
            self.send_reply(line, "How to run your own bot: lichess.org/api#tag/Chess-Bot")
        if cmd == "commands" or cmd == "help":
            msg = "Supported commands: !name, !eval, !id, !leela, !hardware, !info, and !howto"
            self.send_reply(line, msg)
        if cmd == "eval":
            stats = self.engine.get_stats(True)
            self.send_reply(line, ", ".join(stats))
        if cmd == "id":
            self.send_reply(line, "ID {}".format(ID))
        if cmd == "elsie" or cmd == "leela" or cmd == "leelachess":
            responses = ["Stop it. Let me focus!", "Yes?", "Like what you see? Help me improve at: {}".format(LINKS["LCzero"])]
            self.send_reply(line, random.choice(responses))
        if cmd == "info":
            for name, url in LINKS.items():
                self.send_reply(line, "{}: {}".format(name, url))
        if cmd == "hardware" or cmd == "gpu":
            self.send_reply(line, "GTX 1050 Ti 4GB, i7-3770 @ 3.40 GHz, Ubuntu 16.04, Linux 4.4.0")


    def send_reply(self, line, reply):
        self.xhr.chat(self.game.id, line.room, reply)


class ChatLine():
    def __init__(self, json):
        self.room = json.get("room")
        self.username = json.get("username")
        self.text = json.get("text")
