# lichess-bot
A bridge between [Lichess API](https://lichess.org/api#tag/Chess-Bot) and bots.


## How to Install
- NOTE: Currently, only Python3 is supported
- (For convinience of Windows users) Here is a video on how to install the bot: (https://youtu.be/AuncFctntYs). Or you can proceed to these steps. If you don't have Python, you may download it here: (https://www.python.org/downloads/). When installing it, enable "add Python to PATH", then go to custom installation and enable all options (especially "install for all users"), except the last. It's better to install Python in a path without spaces, like "C:\Python\. To type commands it's better to use PowerShell. Go to Start menu and type "PowerShell". Then you may need to upgrade pip. Execute "python -m pip install --upgrade pip" in PowerShell. 
- Download the repo into lichess-bot directory
- Navigate to the directory in cmd/Terminal: `cd lichess-bot` (for Windows users: you may need to type full adress, like "cd C:\chess\lichess-bot")
- Install virtualenv: `pip install virtualenv`
- Setup virtualenv:
```
virtualenv .venv -p python3 (if you only have the last version of Python, you don't need to add "3" to "python") #if this fails you probably need to add Python3 to your PATH
source .venv/bin/activate #for Windows: ./.venv/Scripts/activate (This may not work on Windows, and you need to execute "Set-ExecutionPolicy RemoteSigned" first and choose "Y" there)
pip install -r requirements.txt
```
- Create your config file wih `cp config.yml.default config.yml`
- Edit the variants: `supported_variants` and time controls: `supported_tc` from the config.yml as necessary


## Lichess OAuth
- Create an account for your bot on [Lichess.org](https://lichess.org/signup)
- NOTE: If you have previously played games on an existing account, you will not be able to use it as a bot account
- Once your account has been created and you are logged in, [create a personal OAuth2 token](https://lichess.org/account/oauth/token) with the "Play bot moves" selected and add a description
- A `token` e.g. `Xb0ddNrLabc0lGK2` will be displayed. Store this in `config.yml` as the `token` field
- NOTE: You won't see this token again on Lichess.


## Setup Engine
- Place your engine(s) in the `engine.dir` directory
- In `config.yml`, enter the binary name as the `engine.name` field (In Windows you may need to type a name with ".exe", like "lczero.exe")
- Leave the `weights` field empty or see LeelaChessZero section for Neural Nets


## Lichess Upgrade to Bot Account
**WARNING** This is irreversible. [Read more about upgrading to bot account](https://lichess.org/api#operation/botAccountUpgrade).
- run `python main.py -u`


## LeelaChessZero
- Download the weights for the id you want to play from here: http://lczero.org/networks
- Extract the weights from the zip archive and rename it to `latest.txt`
- Download the lczero binary from here: https://github.com/glinscott/leela-chess/releases
- Copy both the files into the `engine.dir` directory
- Change the `engine.name` and `engine.weights` keys in config.yml to `lczero` and `latest.txt`
- You can specify the number of `engine.threads` in the config.yml file as well
- To start: `python main.py`


# Acknowledgements
Thanks to the Lichess team, especially T. Alexander Lystad and Thibault Duplessis for working with the LeelaChessZero
team to get this API up. Thanks to the Niklas Fiekas and his [python-chess](https://github.com/niklasf/python-chess) code which allows engine communication seamlessly.

# License
lichess-bot is licensed under the AGPLv3 (or any later version at your option). Check out LICENSE.txt for the full text.
