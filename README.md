# lichess-bot
[![Python Build](https://github.com/lichess-bot-devs/lichess-bot/actions/workflows/python-build.yml/badge.svg)](https://github.com/lichess-bot-devs/lichess-bot/actions/workflows/python-build.yml)
[![Python Test](https://github.com/lichess-bot-devs/lichess-bot/actions/workflows/python-test.yml/badge.svg)](https://github.com/lichess-bot-devs/lichess-bot/actions/workflows/python-test.yml)
[![Mypy](https://github.com/lichess-bot-devs/lichess-bot/actions/workflows/mypy.yml/badge.svg)](https://github.com/lichess-bot-devs/lichess-bot/actions/workflows/mypy.yml)

A bridge between [Lichess Bot API](https://lichess.org/api#tag/Bot) and bots.

## Features
Supports:
- Evry variant and time control
- UCI, XBoard, and Homemade engines
- Matchmaking
- Offering Draw / Resigning
- Saving games as PGN
- Opening Books
- Online Opening Books
- Endgame Tablebases
- Online Endgame Tablebases

## How to Install
### Mac/Linux:
- **NOTE: Only Python 3.9 or later is supported!**
- Download the repo into lichess-bot directory.
- Navigate to the directory in cmd/Terminal: `cd lichess-bot`.
- Install pip: `apt install python3-pip`.
  - In non-Ubuntu distros, replace `apt` with the correct package manager (`pacman` in Arch, `dnf` in Fedora, `brew` in Mac, etc.), package name, and installation command.
- Install virtualenv: `apt install python3-virtualenv`.
- Setup virtualenv: `apt install python3-venv`.
```
python3 -m venv venv # If this fails you probably need to add Python3 to your PATH.
virtualenv venv -p python3
source ./venv/bin/activate
python3 -m pip install -r requirements.txt
```
- Copy `config.yml.default` to `config.yml`.
- Edit the variants: `supported_variants` and time controls: `supported_tc` from the `config.yml` file as necessary.

### Windows:
- **NOTE: Only Python 3.9 or later is supported!**
- If needed, install Python:
  - [Download Python here](https://www.python.org/downloads/).
  - When installing, enable "add Python to PATH".
  - If the Python version is at least 3.10, a default local install works.
  - If the Python version is 3.9, choose "Custom installation", keep the defaults on the Optional Features page, and choose "Install for all users" in the Advanced Options page.
- Start Terminal, PowerShell, cmd, or your preferred command prompt.
- Upgrade pip: `python -m pip install --upgrade pip`.
- Download the repo into lichess-bot directory.
- Navigate to the directory: `cd [folder's address]` (for example, `cd C:\Users\username\repos\lichess-bot`).
- Install virtualenv: `pip install virtualenv`.
- Setup virtualenv:
```
python -m venv venv # If this fails you probably need to add Python3 to your PATH.
venv\Scripts\activate
pip install -r requirements.txt
```
PowerShell note: If the `activate` command does not work in PowerShell, execute `Set-ExecutionPolicy RemoteSigned` first and choose `Y` there (you may need to run Powershell as administrator). After you execute the script, change execution policy back with `Set-ExecutionPolicy Restricted` and pressing `Y`.
- Copy `config.yml.default` to `config.yml`.
- Edit the variants: `supported_variants` and time controls: `supported_tc` from the `config.yml` file as necessary (use "#" to disable certain ones).

## Lichess OAuth
- Create an account for your bot on [Lichess.org](https://lichess.org/signup).
- **NOTE: If you have previously played games on an existing account, you will not be able to use it as a bot account.**
- Once your account has been created and you are logged in, [create a personal OAuth2 token with the "Play games with the bot API" (`bot:play`) scope](https://lichess.org/account/oauth/token/create?scopes[]=bot:play&description=lichess-bot) selected and a description added.
- A `token` (e.g. `xxxxxxxxxxxxxxxx`) will be displayed. Store this in the `config.yml` file as the `token` field. You can also set the token in the environment variable `$LICHESS_BOT_TOKEN`.
- **NOTE: You won't see this token again on Lichess, so do save it.**

## Setup Engine
Within the file `config.yml`:
- Enter the directory containing the engine executable in the `engine: dir` field.
- Enter the executable name in the `engine: name` field (In Windows you may need to type a name with ".exe", like "lczero.exe")
- If you want the engine to run in a different directory (e.g., if the engine needs to read or write files at a certain location), enter that directory in the `engine: working_dir` field.
  - If this field is blank or missing, the current directory will be used.
  - IMPORTANT NOTE: If this field is used, the running engine will look for files and directories (Syzygy tablebases, for example) relative to this path, not the directory where lichess-bot was launched. Files and folders specified with absolute paths are unaffected.
- Leave the `weights` field empty or see [LeelaChessZero section](#leelachesszero) for Neural Nets

As an optional convenience, there is a folder named `engines` within the lichess-bot folder where you can copy your engine and all the files it needs. This is the default executable location in the `config.yml.default` file.

### Engine Configuration
See the [lichess-bot wiki](https://github.com/AttackingOrDefending/lichess-bot/wiki/Configure-lichess-bot)

## Lichess Upgrade to Bot Account
**WARNING: This is irreversible. [Read more about upgrading to bot account](https://lichess.org/api#operation/botAccountUpgrade).**
- run `python3 lichess-bot.py -u`.

## To Run
After activating the virtual environment created in the installation steps (the `source` line for Linux and Macs or the `activate` script for Windows), run
```
python3 lichess-bot.py
```
The working directory for the engine execution will be the lichess-bot directory. If your engine requires files located elsewhere, make sure they are specified by absolute path or copy the files to an appropriate location inside the lichess-bot directory.

To output more information (including your engine's thinking output and debugging information), the `-v` option can be passed to lichess-bot:
```
python3 lichess-bot.py -v
```

If you want to disable automatic logging:
```
python3 lichess-bot.py --disable_auto_logging
```

If you want to record the output to a log file, add the `-l` or `--logfile` along with a file name:
```
python3 lichess-bot.py --logfile log.txt
```

## To Quit
- Press `CTRL+C`.
- It may take some time to quit.

# Acknowledgements
Thanks to the Lichess team, especially T. Alexander Lystad and Thibault Duplessis for working with the LeelaChessZero team to get this API up. Thanks to the [Niklas Fiekas](https://github.com/niklasf) and his [python-chess](https://github.com/niklasf/python-chess) code which allows engine communication seamlessly.

# License
lichess-bot is licensed under the AGPLv3 (or any later version at your option). Check out the [LICENSE file](/LICENSE) for the full text.
