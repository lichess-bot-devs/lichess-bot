class Conversation():
    def __init__(self, game, xhr):
        self.game = game
        self.xhr = xhr

    def react(self, line):
        print("*** {} [{}] {}: {}".format(self.game.url(), line.room, line.username, line.text))
        if (line.username == self.game.username):
            return
        # add your chat commands here. Silly example: self.parrot(line)
        pass

    def parrot(self, line):
        self.xhr.chat(self.game.id, line.room, "{} said \"{}\"".format(line.username, line.text))


class ChatLine():
    def __init__(self, json):
        self.room = json.get("room")
        self.username = json.get("username")
        self.text = json.get("text")
