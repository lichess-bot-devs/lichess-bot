# lichess-bot

[![Python Build](https://github.com/ShailChoksi/lichess-bot/actions/workflows/python-build.yml/badge.svg)](https://github.com/ShailChoksi/lichess-bot/actions/workflows/python-build.yml)

A bridge between [Lichess API](https://lichess.org/api#tag/Bot) and bots.


## How to Install

### Mac/Linux:
- NOTE: Only Python 3.7 or later is supported!
- Download the repo into lichess-bot directory
- Navigate to the directory in cmd/Terminal: `cd lichess-bot`
- Install pip: `apt install python3-pip`
- Install virtualenv: `pip install virtualenv`
- Setup virtualenv: `apt install python3-venv`
```
python3 -m venv venv #if this fails you probably need to add Python3 to your PATH
virtualenv venv -p python3 #if this fails you probably need to add Python3 to your PATH
source ./venv/bin/activate
python3 -m pip install -r requirements.txt
```
- Copy `config.yml.default` to `config.yml`
- Edit the variants: `supported_variants` and time controls: `supported_tc` from the config.yml as necessary

### Windows:
- Here is a video on how to install the bot: (https://youtu.be/w-aJFk00POQ). Or you may proceed to the next steps.
- NOTE: Only Python 3.7 or later is supported!
- If you don't have Python, you may download it here: (https://www.python.org/downloads/). When installing it, enable "add Python to PATH", then go to custom installation (this may be not necessary, but on some computers it won't work otherwise) and enable all options (especially "install for all users"), except the last . It's better to install Python in a path without spaces, like "C:\Python\".
- To type commands it's better to use PowerShell. Go to Start menu and type "PowerShell" (you may use cmd too, but sometimes it may not work).
- Then you may need to upgrade pip. Execute "python -m pip install --upgrade pip" in PowerShell.
- Download the repo into lichess-bot directory.
- Navigate to the directory in PowerShell: `cd [folder's adress]` (like "cd C:\chess\lichess-bot").
- Install virtualenv: `pip install virtualenv`.
- Setup virtualenv:
```
python -m venv .venv (if this fails you probably need to add Python to your PATH)
./.venv/Scripts/Activate.ps1 (.\.venv\Scripts\activate.bat should work in cmd in administator mode) (This may not work on Windows, and in this case you need to execute "Set-ExecutionPolicy RemoteSigned" first and choose "Y" there [you may need to run Powershell as administrator]. After you executed the script, change execution policy back with "Set-ExecutionPolicy Restricted" and pressing "Y")
pip install -r requirements.txt
```
- Copy `config.yml.default` to `config.yml`
- Edit the variants: `supported_variants` and time controls: `supported_tc` from the config.yml as necessary (use # to disable certain ones)


## Lichess OAuth
- Create an account for your bot on [Lichess.org](https://lichess.org/signup)
- NOTE: If you have previously played games on an existing account, you will not be able to use it as a bot account
- Once your account has been created and you are logged in, [create a personal OAuth2 token](https://lichess.org/account/oauth/token/create?scopes[]=bot:play&description=lichess-bot) with the "Play as a bot" selected and add a description
- A `token` e.g. `Xb0ddNrLabc0lGK2` will be displayed. Store this in `config.yml` as the `token` field. You can also set the token in the environment variable `$LICHESS_BOT_TOKEN`.
- NOTE: You won't see this token again on Lichess.


## Setup Engine
- Place your engine(s) in the `engine: dir` directory
- In `config.yml`, enter the binary name as the `engine: name` field (In Windows you may need to type a name with ".exe", like "lczero.exe")
- Leave the `weights` field empty or see LeelaChessZero section for Neural Nets

### Engine Configuration
Besides the above, there are many possible options within `config.yml` for configuring the engine for use with lichess-bot.

- `protocol`: Specify which protocol your engine uses. Choices are
    1. `"uci"` for the [Universal Chess Interface](http://wbec-ridderkerk.nl/html/UCIProtocol.html)
    2. `"xboard"` for the XBoard/WinBoard/[Chess Engine Communication Protocol](https://www.gnu.org/software/xboard/engine-intf.html)
    3. `"homemade"` if you want to write your own engine in Python within lichess-bot. See [**Creating a custom bot**](#creating-a-custom-bot) below.
- `ponder`: Specify whether your bot will ponder--i.e., think while the bot's opponent is choosing a move.
- `polyglot`: Tell lichess-bot whether your bot should use an opening book. Multiple books can be specified for each chess variant.
    - `enabled`: Whether to use the book at all.
    - `book`: A nested list of books. The next indented line should list a chess variant (`standard`, `3check`, `horde`, etc.) followed on succeeding indented lines with paths to the book files. See `config.yml.default` for examples.
- `engine_options`: Command line options to pass to the engine on startup. For example, the `config.yml.default` has the configuration
```yml
  engine_options:
    cpuct: 3.1
```
This would create the command-line option `--cpuct=3.1` to be used when starting the engine, like this for the engine lc0: `lc0 --cpuct=3.1`. Any number of options can be listed here, each getting their own command-line option.
- `uci_options`: A list of options to pass to a UCI engine after startup. Different engines have different options, so treat the options in `config.yml.default` as templates and not suggestions. When UCI engines start, they print a list of configurations that can modify their behavior. For example, Stockfish 13 prints the following when run at the command line:
```
id name Stockfish 13
id author the Stockfish developers (see AUTHORS file)

option name Debug Log File type string default 
option name Contempt type spin default 24 min -100 max 100
option name Analysis Contempt type combo default Both var Off var White var Black var Both
option name Threads type spin default 1 min 1 max 512
option name Hash type spin default 16 min 1 max 33554432
option name Clear Hash type button
option name Ponder type check default false
option name MultiPV type spin default 1 min 1 max 500
option name Skill Level type spin default 20 min 0 max 20
option name Move Overhead type spin default 10 min 0 max 5000
option name Slow Mover type spin default 100 min 10 max 1000
option name nodestime type spin default 0 min 0 max 10000
option name UCI_Chess960 type check default false
option name UCI_AnalyseMode type check default false
option name UCI_LimitStrength type check default false
option name UCI_Elo type spin default 1350 min 1350 max 2850
option name UCI_ShowWDL type check default false
option name SyzygyPath type string default <empty>
option name SyzygyProbeDepth type spin default 1 min 1 max 100
option name Syzygy50MoveRule type check default true
option name SyzygyProbeLimit type spin default 7 min 0 max 7
option name Use NNUE type check default true
option name EvalFile type string default nn-62ef826d1a6d.nnue
uciok
```
Any of the names following `option name` can be listed in `uci_options` in order to configure the Stockfish engine.
```yml
  uci_options:
    Move Overhead: 100
    Skill Level: 10
```
The exception to this are the options `uci_chess960`, `uci_variant`, `multipv`, and `ponder`. These will be handled by lichess-bot after a game starts and should not be listed in `config.yml`. Also, if an option is listed under `uci_options` that is not in the list printed by the engine, it will cause an error when the engine starts because the engine won't understand the option. The word after `type` indicates the expected type of the options: `string` for a text string, `spin` for a numeric value, `check` for a boolean True/False value.

One last option is `go_commands`. Beneath this option, arguments to the UCI `go` command can be passed. For example,
```yml
  go_commands:
    nodes: 1
    depth: 5
    movetime: 1000
```
will append `nodes 1 depth 5 movetime 1000` to the command to start thinking of a move: `go startpos e2e4 e7e5 ...`.

- `xboard_options`: A list of options to pass to an XBoard engine after startup. Different engines have different options, so treat the options in `config.yml.default` as templates and not suggestions. When XBoard engines start, they print a list of configurations that can modify their behavior. The configurable options will be prefixed with `feature option`. Some examples may include
```
feature option="Add Noise -check VALUE"
feature option="PGN File -string VALUE"
feature option="CPU Count -spin VALUE MIN MAX"`
```
Any of the options can be listed under `xboard_options` in order to configure the XBoard engine.
```yml
  xboard_options:
    Add Noise: False
    PGN File: lichess_games.pgn
    CPU Count: 1
```
The exceptions to this are the options `multipv`, and `ponder`. These will be handled by lichess-bot after a game starts and should not be listed in `config.yml`. Also, if an option is listed under `xboard_options` that is not in the list printed by the engine, it will cause an error when the engine starts because the engine won't know how to handle the option. The word prefixed with a hyphen indicates the expected type of the options: `-string` for a text string, `-spin` for a numeric value, `-check` for a boolean True/False value.

One last option is `go_commands`. Beneath this option, commands prior to the `go` command can be passed. For example,
```yml
  go_commands:
    depth: 5
```
will precede the `go` command to start thinking with `sd 5`. The other `go_commands` list above for UCI engines (`nodes` and `movetime`) are not valid for XBoard engines and will detrimentally affect their time control.

- `abort_time`: How many seconds to wait before aborting a game due to opponent inaction. This only applies during the first six moves of the game.
- `fake_think_time`: Artificially slow down the engine to simulate a person thinking about a move. The amount of thinking time decreases as the game goes on.
- `rate_limiting_delay`: For extremely fast games, the lichess.org servers may respond with an error if too many moves are played to quickly. This option avoids this problem by pausing for a specified number of milliseconds after submitting a move before making the next move.
- `move_overhead`: To prevent losing on time due to network lag, subtract this many milliseconds from the time to think on each move.

- `correspondence` These options control how the engine behaves during correspondence games.
  - `move_time`: How many seconds to think for each move.
  - `checkin_period`: How often (in seconds) to reconnect to games to check for new moves after disconnecting.
  - `disconnect_time`: How many seconds to wait after the bot makes a move for an opponent to make a move. If no move is made during the wait, disconnect from the game.
  - `ponder`: Whether the bot should ponder during the above waiting period.

- `challenge`: Control what kind of games for which the bot should accept challenges. All of the following options must be satisfied by a challenge to be accepted.
  - `concurrency`: The maximum number of games to play simultaneously.
  - `sort_by`: Whether to start games by the best rated/titled opponent `"best"` or by first-come-first-serve `"first"`.
  - `accept_bot`: Whether to accept challenges from other bots.
  - `only_bot`: Whether to only accept challenges from other bots.
  - `max_increment`: The maximum value of time increment.
  - `min_increment`: The minimum value of time increment.
  - `max_base`: The maximum base time for a game.
  - `min_base`: The minimum base time for a game.
  - `variants`: An indented list of chess variants that the bot can handle.
```yml
  variants:
    - standard
    - horde
    - antichess
    # etc.
```
  - `time_controls`: An indented list of acceptable time control types from `bullet` to `correspondence`.
```yml
  time_controls:
    - bullet
    - blitz
    - rapid
    - classical
    - correpondence
```
  - `modes`: An indented list of acceptable game modes (`rated` and/or `casual`).
```yml
  modes:
    -rated
    -casual
```

## Lichess Upgrade to Bot Account
**WARNING** This is irreversible. [Read more about upgrading to bot account](https://lichess.org/api#operation/botAccountUpgrade).
- run `python lichess-bot.py -u`

## To Run
After activating the virtual environment created in the installation steps (the `source` line for Linux and Macs or the `activate` script for Windows), run
```python
python lichess-bot.py
```
The working directory for the engine execution will be the lichess-bot directory. If your engine requires files located elsewhere, make sure they are specified by absolute path or copy the files to an appropriate location inside the lichess-bot directory.

To output more information (including your engine's thinking output and debugging information), the `-v` option can be passed to lichess-bot:
```python
python lichess-bot.py -v
```

## To Quit
- Press CTRL+C
- It may take some time to quit

## LeelaChessZero (Mac/Linux)

- Download the weights for the id you want to play from here: https://lczero.org/play/networks/bestnets/
- Extract the weights from the zip archive and rename it to `latest.txt`
- For Mac/Linux, build the lczero binary yourself following [LeelaChessZero/lc0/README](https://github.com/LeelaChessZero/lc0/blob/master/README.md)
- Copy both the files into the `engine.dir` directory
- Change the `engine.name` and `engine.engine_options.weights` keys in config.yml to `lczero` and `weights.pb.gz`
- You can specify the number of `engine.uci_options.threads` in the config.yml file as well
- To start: `python lichess-bot.py`

## LeelaChessZero (Windows CPU 2021)

- For Windows modern CPUs, download the lczero binary from https://github.com/LeelaChessZero/lc0/releases ex: `lc0-v0.27.0-windows-cpu-dnnl.zip`
- Unzip the file, it comes with lc0.exe , dnnl.dll, and a weights file ex: `703810.pb.gz` (amongst other files)
- all three main files need to be copied to the engines directory
- the lc0.exe should be doubleclicked and the windows safesearch warning about it being unsigned should be cleared (be careful and be sure you have the genuine file)
- Change the `engine.name` key in config.yml to `lc0.exe`, no need to edit config.yml concerning the weights file as the lc0.exe will use whatever *.pb.gz is in the same folder (have only one *pb.gz in the engines directory)
- To start: `python lichess-bot.py` 

## For Docker

Use https://github.com/vochicong/lc0-nvidia-docker to easily run lc0 and lichess-bot
inside a Docker container.

## Creating a homemade bot

As an alternative to creating an entire chess engine and implementing one of the communiciation protocols (UCI or XBoard), a bot can also be created by writing a single class with a single method. The `search()` method in this new class takes the current board and the game clock as arguments and should return a move based on whatever criteria the coder desires.

Steps to create a homemade bot:

1. Do all the steps in the [How to Install](#how-to-install)
2. In the `config.yml`, change the engine protocol to `homemade`
3. Create a class in some file that extends `MinimalEngine` (in `strategies.py`).
    - Look at the `strategies.py` file to see some examples.
    - If you don't know what to implement, look at the `EngineWrapper` or `UCIEngine` class.
        - You don't have to create your own engine, even though it's an "EngineWrapper" class.<br>
          The examples just implement `search`.
4. In the `config.yml`, change the name from engine_name to the name of your class
    - In this case, you could change it to:
      
      `name: "RandomMove"`

## Tips & Tricks
- You can specify a different config file with the `--config` argument.
- Here's an example systemd service definition:
```
[Unit]
Description=lichess-bot
After=network-online.target
Wants=network-online.target

[Service]
Environment="PYTHONUNBUFFERED=1"
ExecStart=/usr/bin/python3 /home/thibault/lichess-bot/lichess-bot.py
WorkingDirectory=/home/thibault/lichess-bot/
User=thibault
Group=thibault
Restart=always

[Install]
WantedBy=multi-user.target
```

# Acknowledgements
Thanks to the Lichess team, especially T. Alexander Lystad and Thibault Duplessis for working with the LeelaChessZero
team to get this API up. Thanks to the Niklas Fiekas and his [python-chess](https://github.com/niklasf/python-chess) code which allows engine communication seamlessly.

# License
lichess-bot is licensed under the AGPLv3 (or any later version at your option). Check out LICENSE.txt for the full text.
