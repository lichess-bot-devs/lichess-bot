import random

LINKS = {
    "lczero": "http://lczero.org/",
    "github": "https://github.com/careless25/lichess-bot",
    "api": "https://lichess.org/api#tag/Chess-Bot"
}

class Conversation():
    def __init__(self, game, engine, xhr):
        self.game = game
        self.engine = engine
        self.xhr = xhr

    command_prefix = "!"

    def react(self, line):
        print("*** {} [{}] {}: {}".format(self.game.url(), line.room, line.username, line.text.encode("utf-8")))
        if (line.text[0] == self.command_prefix):
            self.command(line, line.text[1:].lower())
        pass

    def command(self, line, cmd):
        if cmd == "commands" or cmd == "help":
            msg = "Supported commands: !name, !eval, !id, !leela, !hardware and !info."
            self.send_reply(line, msg)
        if cmd == "name" or cmd == "engine":
            self.send_reply(line, self.engine.name() + " ID 125")
        if cmd == "eval" or cmd == "stats":
            stats = self.engine.get_stats(True)
            self.send_reply(line, ", ".join(stats))
        if cmd == "id" or cmd == "network":
            self.send_reply(line, "ID 125")
        if cmd.lower() == "elsie" or cmd.lower() == "leela" or cmd.lower() == "leelachess":
            responses = ["Stop it. Let me focus!", "Yes?", "{} gives me nightmares.".format(self.game.opponent.name)]
            self.send_reply(line, random.choice(responses))
        if cmd.lower() == "info" or cmd.lower() == "links":
            for name, url in LINKS.items():
                self.send_reply(line, "{}: {}".format(name, url))
        if cmd.lower() == "hardware" or cmd.lower() == "gpu":
            self.send_reply(line, "Running on GTX 1060 6GB, i5-6600K @ 3.50 GHz, 16 GB RAM, Windows 10 Pro")

    def send_reply(self, line, reply):
        self.xhr.chat(self.game.id, line.room, reply)


class ChatLine():
    def __init__(self, json):
        self.room = json.get("room")
        self.username = json.get("username")
        self.text = json.get("text")
