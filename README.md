# lichess-bot
[![Python Build](https://github.com/ShailChoksi/lichess-bot/actions/workflows/python-build.yml/badge.svg)](https://github.com/ShailChoksi/lichess-bot/actions/workflows/python-build.yml)
[![Python Test](https://github.com/ShailChoksi/lichess-bot/actions/workflows/python-test.yml/badge.svg)](https://github.com/ShailChoksi/lichess-bot/actions/workflows/python-test.yml)

A bridge between [Lichess Bot API](https://lichess.org/api#tag/Bot) and bots.

## How to Install
### Mac/Linux:
- **NOTE: Only Python 3.7 or later is supported!**
- Download the repo into lichess-bot directory.
- Navigate to the directory in cmd/Terminal: `cd lichess-bot`.
- Install pip: `apt install python3-pip`.
- Install virtualenv: `pip install virtualenv`.
- Setup virtualenv: `apt install python3-venv`.
```python
python3 -m venv venv # If this fails you probably need to add Python3 to your PATH.
virtualenv venv -p python3 # If this fails you probably need to add Python3 to your PATH.
source ./venv/bin/activate
python3 -m pip install -r requirements.txt
```
- Copy `config.yml.default` to `config.yml`.
- Edit the variants: `supported_variants` and time controls: `supported_tc` from the `config.yml` file as necessary.

### Windows:
- [Here is a video on how to install the bot](https://youtu.be/w-aJFk00POQ). Or you may proceed to the following steps.
- **NOTE: Only Python 3.7 or later is supported!**
- If you don't have Python, you may [download it here](https://www.python.org/downloads/). When installing it, enable "add Python to PATH", then go to custom installation (this may be not necessary, but on some computers it won't work otherwise) and enable all options (especially "install for all users"), except the last. It's better to install Python in a path without spaces, like "C:\Python\".
- To type commands it's better to use PowerShell. Go to Start menu and type "PowerShell" (you may use "cmd" too, but sometimes it may not work).
- Then you may need to upgrade pip. Execute `python3 -m pip install --upgrade pip` in PowerShell.
- Download the repo into lichess-bot directory.
- Navigate to the directory in PowerShell: `cd [folder's adress]` (example, `cd C:\chess\lichess-bot`).
- Install virtualenv: `pip install virtualenv`.
- Setup virtualenv:
```python
python3 -m venv .venv # If this fails you probably need to add Python3 to your PATH.
./.venv/Scripts/Activate.ps1 # `.\.venv\Scripts\activate.bat` should work in cmd in administator mode. This may not work on Windows, and in this case you need to execute "Set-ExecutionPolicy RemoteSigned" first and choose "Y" there (you may need to run Powershell as administrator). After you executed the script, change execution policy back with "Set-ExecutionPolicy Restricted" and pressing "Y".
pip install -r requirements.txt
```
- Copy `config.yml.default` to `config.yml`.
- Edit the variants: `supported_variants` and time controls: `supported_tc` from the `config.yml` file as necessary (use "#" to disable certain ones).

## Lichess OAuth
- Create an account for your bot on [Lichess.org](https://lichess.org/signup).
- **NOTE: If you have previously played games on an existing account, you will not be able to use it as a bot account.**
- Once your account has been created and you are logged in, [create a personal OAuth2 token with the "Play games with the bot API" ('bot:play') scope](https://lichess.org/account/oauth/token/create?scopes[]=bot:play&description=lichess-bot) selected and a description added.
- A `token` (e.g. `xxxxxxxxxxxxxxxx`) will be displayed. Store this in the `config.yml` file as the `token` field. You can also set the token in the environment variable `$LICHESS_BOT_TOKEN`.
- **NOTE: You won't see this token again on Lichess, so do save it.**

## Setup Engine
Within the file `config.yml`:
- Enter the directory containing the engine executable in the `engine: dir` field.
- Enter the executable name in the `engine: name` field (In Windows you may need to type a name with ".exe", like "lczero.exe")
- If you want the engine to run in a different directory (e.g., if the engine needs to read or write files at a certain location), enter that directory in the `engine: working_dir` field.
  - If this field is blank or missing, the current directory will be used.
- Leave the `weights` field empty or see [LeelaChessZero section](#leelachesszero) for Neural Nets

As an optional convenience, there is a folder named `engines` within the lichess-bot folder where you can copy your engine and all the files it needs. This is the default executable location in the `config.yml.default` file.

### Engine Configuration
Besides the above, there are many possible options within `config.yml` for configuring the engine for use with lichess-bot.

- `protocol`: Specify which protocol your engine uses. Choices are
    1. `"uci"` for the [Universal Chess Interface](http://wbec-ridderkerk.nl/html/UCIProtocol.html)
    2. `"xboard"` for the XBoard/WinBoard/[Chess Engine Communication Protocol](https://www.gnu.org/software/xboard/engine-intf.html)
    3. `"homemade"` if you want to write your own engine in Python within lichess-bot. See [**Creating a homemade bot**](#creating-a-homemade-bot) below.
- `ponder`: Specify whether your bot will ponder--i.e., think while the bot's opponent is choosing a move.
- `polyglot`: Tell lichess-bot whether your bot should use an opening book. Multiple books can be specified for each chess variant.
    - `enabled`: Whether to use the book at all.
    - `book`: A nested list of books. The next indented line should list a chess variant (`standard`, `3check`, `horde`, etc.) followed on succeeding indented lines with paths to the book files. See `config.yml.default` for examples.
- `draw_or_resign`: This section allows your bot to resign or offer/accept draw based on the evaluation by the engine. XBoard engines can resign and offer/accept draw without this feature enabled.
    - `resign_enabled`: Whether the bot is allowed to resign based on the evaluation.
    - `resign_score`: The engine evaluation has to be less than or equal to `resign_score` for the bot to resign.
    - `resign_for_egtb_minus_two`: If true the bot will resign in positions where the online_egtb returns a wdl of -2.
    - `resign_moves`: The evaluation has to be less than or equal to `resign_score` for `resign_moves` amount of moves for the bot to resign.
    - `offer_draw_enabled`: Whether the bot is allowed to offer/accept draw based on the evaluation.
    - `offer_draw_score`: The absolute value of the engine evaluation has to be less than or equal to `offer_draw_score` for the bot to offer/accept draw.
    - `offer_draw_for_egtb_zero`: If true the bot will offer/accept draw in positions where the online_egtb returns a wdl of 0.
    - `offer_draw_moves`: The absolute value of the evaluation has to be less than or equal to `offer_draw_score` for `offer_draw_moves` amount of moves for the bot to offer/accept draw.
    - `offer_draw_pieces`: The bot only offers/accepts draws if the position has less than or equal to `offer_draw_pieces` pieces.
- `online_moves`: This section gives your bot access to various online resources for choosing moves like opening books and endgame tablebases. This can be a supplement or a replacement for chess databases stored on your computer. There are three sections that correspond to three different online databases:
    1. `chessdb_book`: Consults a [Chinese chess position database](https://www.chessdb.cn/), which also hosts a xiangqi database.
    2. `lichess_cloud_analysis`: Consults [Lichess' own position analysis database](https://lichess.org/api#operation/apiCloudEval).
    3. `online_egtb`: Consults either the online Syzygy 7-piece endgame tablebase [hosted by Lichess](https://lichess.org/blog/W3WeMyQAACQAdfAL/7-piece-syzygy-tablebases-are-complete) or the chessdb listed above.
    - Configurations common to all:
        - `enabled`: Whether to use the database at all.
        - `min_time`: The minimum time in seconds on the game clock necessary to allow the online database to be consulted.
    - Configurations only in `chessdb_book` and `lichess_cloud_analysis`:
        - `move_quality`: Choice of `"all"` (`chessdb_book` only), `"good"`, or `"best"`.
            - `all`: Choose a random move from all legal moves.
            - `best`: Choose only the highest scoring move.
            - `good`: Choose randomly from the top moves. In `lichess_cloud_analysis`, the top moves list is controlled by `max_score_difference`. In `chessdb_book`, the top list is controlled by the online source.
        - `min_depth`: The minimum search depth for a move evaluation for a database move to be accepted.
    - Configurations only in `chessdb_book`:
        - `contribute`: Send the current board position to chessdb for later analysis.
    - Configurations only in `lichess_cloud_analysis`:
        - `max_score_difference`: When `move_quality` is set to `"good"`, this option specifices the maximum difference between the top scoring move and any other move that will make up the set from which a move will be chosen randomly. If this options is set to 25 and the top move in a position has a score of 100, no move with a score of less than 75 will be returned.
        - `min_knodes`: The minimum number of kilonodes to search. The minimum number of nodes to search is this value times 1000.
    - Configurations only in `online_egtb`:
        -  `max_pieces`: The maximum number of pieces in the current board for which the tablebase will be consulted.
        - `source`: One of `chessdb` or `lichess`. Lichess also has tablebases for atomic and antichess while chessdb only has those for standard.
- `engine_options`: Command line options to pass to the engine on startup. For example, the `config.yml.default` has the configuration
```yml
  engine_options:
    cpuct: 3.1
```
This would create the command-line option `--cpuct=3.1` to be used when starting the engine, like this for the engine lc0: `lc0 --cpuct=3.1`. Any number of options can be listed here, each getting their own command-line option.
- `uci_options`: A list of options to pass to a UCI engine after startup. Different engines have different options, so treat the options in `config.yml.default` as templates and not suggestions. When UCI engines start, they print a list of configurations that can modify their behavior after receiving the string "uci". For example, to find out what options Stockfish 13 supports, run the executable in a terminal, type `uci`, and press Enter. The engine will print the following when run at the command line:
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

- `xboard_options`: A list of options to pass to an XBoard engine after startup. Different engines have different options, so treat the options in `config.yml.default` as templates and not suggestions. When XBoard engines start, they print a list of configurations that can modify their behavior. To see these configurations, run the engine in a terminal, type `xboard`, press Enter, type `protover 2`, and press Enter. The configurable options will be prefixed with `feature option`. Some examples may include
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
  - `greeting`: Send messages via chat to the bot's opponent. The string `{me}` will be replaced by the bot's lichess account name. The string `{opponent}` will be replaced by the opponent's lichess account name. Any other word between curly brackets will be removed. If you want to put a curly bracket in the message, use two: `{{` or `}}`.
    - `hello`: Message to send to opponent before the bot makes its first move.
    - `goodbye`: Message to send to opponent once the game is over.
```yml
  greeting:
    hello: Hi, {opponent}! I'm {me}. Good luck!
    goodbye: Good game!
```

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

## To Quit
- Press `CTRL+C`.
- It may take some time to quit.

## <a name="leelachesszero"></a> LeelaChessZero: Mac/Linux
- Download the weights for the id you want to play from [here](https://lczero.org/play/networks/bestnets/).
- Extract the weights from the zip archive and rename it to `latest.txt`.
- For Mac/Linux, build the lczero binary yourself following [LeelaChessZero/lc0/README](https://github.com/LeelaChessZero/lc0/blob/master/README.md).
- Copy both the files into the `engine.dir` directory.
- Change the `engine.name` and `engine.engine_options.weights` keys in `config.yml` file to `lczero` and `weights.pb.gz`.
- You can specify the number of `engine.uci_options.threads` in the `config.yml` file as well.
- To start: `python3 lichess-bot.py`.

## LeelaChessZero: Windows CPU 2021
- For Windows modern CPUs, download the lczero binary from the [latest Lc0 release](https://github.com/LeelaChessZero/lc0/releases) (e.g. `lc0-v0.27.0-windows-cpu-dnnl.zip`).
- Unzip the file, it comes with `lc0.exe` , `dnnl.dll`, and a weights file example, `703810.pb.gz` (amongst other files).
- All three main files need to be copied to the engines directory.
- The `lc0.exe` should be doubleclicked and the windows safesearch warning about it being unsigned should be cleared (be careful and be sure you have the genuine file).
- Change the `engine.name` key in the `config.yml` file to `lc0.exe`, no need to edit the `config.yml` file concerning the weights file as the `lc0.exe` will use whatever `*.pb.gz` is in the same folder (have only one `*pb.gz` file in the engines directory).
- To start: `python3 lichess-bot.py`.

## LeelaChessZero: Docker container
Use https://github.com/vochicong/lc0-nvidia-docker to easily run lc0 and lichess-bot inside a Docker container.

## <a name="creating-a-homemade-bot"></a> Creating a homemade bot
As an alternative to creating an entire chess engine and implementing one of the communiciation protocols (`UCI` or `XBoard`), a bot can also be created by writing a single class with a single method. The `search()` method in this new class takes the current board and the game clock as arguments and should return a move based on whatever criteria the coder desires.

Steps to create a homemade bot:

1. Do all the steps in the [How to Install](#how-to-install)
2. In the `config.yml`, change the engine protocol to `homemade`
3. Create a class in some file that extends `MinimalEngine` (in `strategies.py`).
    - Look at the `strategies.py` file to see some examples.
    - If you don't know what to implement, look at the `EngineWrapper` or `UCIEngine` class.
        - You don't have to create your own engine, even though it's an "EngineWrapper" class.<br>
The examples just implement `search`.
4. In the `config.yml`, change the name from `engine_name` to the name of your class
    - In this case, you could change it to:

        `name: "RandomMove"`

## Tips & Tricks
- You can specify a different config file with the `--config` argument.
- Here's an example systemd service definition:
```ini
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
Thanks to the Lichess team, especially T. Alexander Lystad and Thibault Duplessis for working with the LeelaChessZero team to get this API up. Thanks to the [Niklas Fiekas](https://github.com/niklasf) and his [python-chess](https://github.com/niklasf/python-chess) code which allows engine communication seamlessly.

# License
lichess-bot is licensed under the AGPLv3 (or any later version at your option). Check out the [LICENSE file](/LICENSE) for the full text.
