class Conversation():
    def __init__(self, game, engine, xhr):
        self.game = game
        self.engine = engine
        self.xhr = xhr

    command_prefix = "!"

    def react(self, line):
        print("*** {} [{}] {}: {}".format(self.game.url(), line.room, line.username, line.text.encode("utf-8")))
        if (line.text[0] == self.command_prefix):
            self.command(line, line.text[1:])
        pass

    def command(self, line, cmd):
        if cmd == "name" or cmd == "engine":
            self.send_reply(line, self.engine.name)

    def send_reply(self, line, reply):
        self.xhr.chat(self.game.id, line.room, reply)


class ChatLine():
    def __init__(self, json):
        self.room = json.get("room")
        self.username = json.get("username")
        self.text = json.get("text")
