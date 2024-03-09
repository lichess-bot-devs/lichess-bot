## Extra customizations

If your bot has more complex requirements than can be expressed in the configuration file, create a file named `extra_game_handlers.py` in the main lichess-bot directory.
Within this file, write whatever code is needed.

Each section below describes a customization.
Only one function is needed to make that customization work.
However, if writing other functions makes implementing the customization easier, do so.
Only the named function will be used in lichess-bot.


### Filtering challenges

The function `is_supported_extra()` allows for finer control over which challenges from other players are accepted.
It must accept a `Challenge` instance (see `lib/model.py`) as an argument and return `True` to accept the challenge or `False` to reject it.
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
