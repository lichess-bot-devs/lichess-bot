# lichess-uci-bot
A bridge between Lichess API and UCI bots. Makes use of python-chess: https://github.com/niklasf/python-chess


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
- Place your engine(s) in the `engines` directory


## Config
- Edit the config.yml file and update the token field with your token
- In the `engine` field, enter the binary name
- Leave the `weights` field empty or see LeelaChessZero section for Neural Nets


## Lichess Upgrade to Bot Account
This is irreversible. [Read more about upgrading to bot account](https://lichess.org/api#operation/botAccountUpgrade).
- run `python main.py -u`


## LeelaChessZero
- Download the weights for the id you want to play from here: http://lczero.org/networks
- Extract the weights from the zip archive and rename it to `latest.txt`
- Download the lczero binary from here: https://github.com/glinscott/leela-chess/releases
- Copy both the files into the `engines` directory
- Change the `engine` and `weights` keys in config.yml to `lczero` and `latest.txt`
- You can specify the number of threads in the config.yml file as well
- To start: `python main.py`


# Acknowledgements
Thanks to the Lichess team, especially T. Alexander Lystad and Thibault Duplessis for working with the LeelaChessZero
team to get this API up. Thanks to the Niklas Fiekas and his python-chess code which allows UCI engine communication seamlessly.

# License
lichess-uci-bot is licensed under the GPL 3 (or any later version at your option). Check out LICENSE.txt for the full text.
