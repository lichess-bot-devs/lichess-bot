## Extra customizations

If your bot has more complex requirements than can be expressed in the configuration file, edit the file named `extra_game_handlers.py` in the main lichess-bot directory.
Within this file, write whatever code is needed.

Each section below describes a customization.
Only one function is needed to make that customization work.
However, if writing other functions makes implementing the customization easier, do so.
Only the named function will be used in lichess-bot.


### Filtering challenges

The function `is_supported_extra()` allows for finer control over which challenges from other players are accepted.
It should use the data in the `Challenge` argument (see `lib/model.py`) and return `True` to accept the challenge or `False` to reject it.
As an example, here's a version that will only only accept games where the bot plays black:
``` python
def is_supported_extra(challenge):
    return challenge.color == "white"
```
For another example, this function will reject any board that contains queens:
``` python
def is_supported_extra(challenge):
    # https://en.wikipedia.org/wiki/Forsyth%E2%80%93Edwards_Notation
    starting_position = challenge.initial_fen
    return starting_position != "startpos" and "Q" not in starting_position.upper()
```
The body of the function can be as complex as needed and combine any conditions to suit the needs of the bot.
Information within the `Challenge` instance is detailed in the [Lichess API documentation](https://lichess.org/api#tag/Bot/operation/apiStreamEvent) (click on 200 under Responses, then select `ChallengeEvent` under Response Schema and expand the `challenge` heading).

### Tailoring engine options

The function `game_specific_options()` can modify the engine options for UCI and XBoard engines based on aspects of the game about to be played.
It use the data in the `Game` argument (see `lib/model.py`) and return a dictionary of `str` to values.
This dictionary will add or replace values in the `uci_options` or `xboard_options` section of the bot's configuration file.
For example, this version of the function will changes the move overhead value for longer games:
``` python
from datetime import timedelta

def game_specific_options(game):
    if game.clock_initial >= timedelta(minutes=5):
        return {"Move Overhead": 5000}
    else:
        return {}
```
Returning an empty dictionary leaves the engine options unchanged.
