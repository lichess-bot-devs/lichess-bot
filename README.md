# lichess-uci-bot
A bridge between Lichess API and UCI bots. Makes use of python-chess.

## How to Install
- Download the repo into lichess-uci-bot directory
- run `pip install -r requirements.txt`

## Lichess OAuth
- Create an account for your bot on Lichess.org
- NOTE: If you have previously played games on an existing account, you will not be able to use it as a bot account
- Once your account has been created and you are logged in, go to: https://lichess.org/account/oauth/token
- Create an access token with the "Play bot moves" selected and add a description
- Click submit!
- A {token} e.g. `stEstTokenLicHeSs` will be displayed. Store this.
- NOTE: You won't see this token again.

## Setup Engine
- create a `engines` directory in the lichess-uci-bot directory
- place your engine(s) in this directory

## Time to Play!
- Start a game in Lichess. Get the {game_id} from the Url e.g. "https://lichess.org/5ekNlPWn" -> `5ekNlPWn` is the game_id
- run `python main.py {token} {game_id} {path_to_engine}` e.g. `python main.py stEstTokenLicHeSs 5ekNlPWn ./engines/stockfish`
- Have fun!

## For LeelaChessZero
- Download the weights for the id you want to play from here: http://lczero.org/networks
- Download the lczero binary from here: https://github.com/glinscott/leela-chess/releases
- Extract the weights file and rename it to latest.txt
- Copy both the files into `engines` directory
- run `python main.py {token} {game_id} {path_to_engine} --weights {path_to_weights}`
- e.g. `python main.py stEstTokenLicHeSs 5ekNlPWn ./engines/lczero --weights ./engines/latest.txt`
