# Configuring lichess-bot
There are many possible options within `config.yml` for configuring lichess-bot.

## Engine options
- `interpreter`: Specify whether your engine requires an interpreter to run (e.g. `java`, `python`).
- `interpreter_options`: A list of options passed to the interpreter (e.g. `-jar` for `java`).
- `protocol`: Specify which protocol your engine uses. Choices are:
    1. `"uci"` for the [Universal Chess Interface](https://wbec-ridderkerk.nl/html/UCIProtocol.html)
    2. `"xboard"` for the XBoard/WinBoard/[Chess Engine Communication Protocol](https://www.gnu.org/software/xboard/engine-intf.html)
    3. `"homemade"` if you want to write your own engine in Python within lichess-bot. See [**Create a homemade engine**](https://github.com/lichess-bot-devs/lichess-bot/wiki/Create-a-homemade-engine).
- `ponder`: Specify whether your bot will ponder--i.e., think while the bot's opponent is choosing a move.
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
The exceptions to this are the options `uci_chess960`, `uci_variant`, `multipv`, and `ponder`. These will be handled by lichess-bot after a game starts and should not be listed in `config.yml`. Also, if an option is listed under `uci_options` that is not in the list printed by the engine, it will cause an error when the engine starts because the engine won't understand the option. The word after `type` indicates the expected type of the options: `string` for a text string, `spin` for a numeric value, `check` for a boolean True/False value.

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
feature option="CPU Count -spin VALUE MIN MAX"
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

## External moves
- `polyglot`: Tell lichess-bot whether your bot should use an opening book. Multiple books can be specified for each chess variant.
    - `enabled`: Whether to use the book at all.
    - `book`: A nested list of books. The next indented line should list a chess variant (`standard`, `3check`, `horde`, etc.) followed on succeeding indented lines with paths to the book files. See `config.yml.default` for examples.
    - `min_weight`: The minimum weight or quality a move must have if it is to have a chance of being selected. If a move cannot be found that has at least this weight, no move will be selected.
    - `selection`: The method for selecting a move. The choices are: `"weighted_random"` where moves with a higher weight/quality have a higher probability of being chosen, `"uniform_random"` where all moves of sufficient quality have an equal chance of being chosen, and `"best_move"` where the move with the highest weight is always chosen.
    - `max_depth`: The maximum number of moves a bot plays before it stops consulting the book. If `max_depth` is 3, then the bot will stop consulting the book after its third move.
- `online_moves`: This section gives your bot access to various online resources for choosing moves like opening books and endgame tablebases. This can be a supplement or a replacement for chess databases stored on your computer. There are four sections that correspond to four different online databases:
    1. `chessdb_book`: Consults a [Chinese chess position database](https://www.chessdb.cn/), which also hosts a xiangqi database.
    2. `lichess_cloud_analysis`: Consults [Lichess's own position analysis database](https://lichess.org/api#operation/apiCloudEval).
    3. `lichess_opening_explorer`: Consults [Lichess's opening explorer](https://lichess.org/api#tag/Opening-Explorer).
    4. `online_egtb`: Consults either the online Syzygy 7-piece endgame tablebase [hosted by Lichess](https://lichess.org/blog/W3WeMyQAACQAdfAL/7-piece-syzygy-tablebases-are-complete) or the chessdb listed above.
    - `max_out_of_book_moves`: Stop using online opening books after they don't have a move for `max_out_of_book_moves` positions. Doesn't apply to the online endgame tablebases.
    - `max_retries`: The maximum amount of retries when getting an online move.
    - `max_depth`: The maximum number of moves a bot can make in the opening before it stops consulting the online opening books. If `max_depth` is 5, then the bot will stop consulting the online books after its fifth move.
    - Configurations common to all:
        - `enabled`: Whether to use the database at all.
        - `min_time`: The minimum time in seconds on the game clock necessary to allow the online database to be consulted.
        - `move_quality`: Choice of `"all"` (`chessdb_book` only), `"good"` (all except `online_egtb`), `"best"`, or `"suggest"` (`online_egtb` only).
            - `all`: Choose a random move from all legal moves.
            - `best`: Choose only the highest scoring move.
            - `good`: Choose randomly from the top moves. In `lichess_cloud_analysis`, the top moves list is controlled by `max_score_difference`. In `chessdb_book`, the top list is controlled by the online source.
            - `suggest`: Let the engine choose between the top moves. The top moves are the all the moves that have the best WDL. Can't be used with XBoard engines.
    - Configurations only in `chessdb_book` and `lichess_cloud_analysis`:
        - `min_depth`: The minimum search depth for a move evaluation for a database move to be accepted.
    - Configurations only in `lichess_cloud_analysis`:
        - `max_score_difference`: When `move_quality` is set to `"good"`, this option specifies the maximum difference between the top scoring move and any other move that will make up the set from which a move will be chosen randomly. If this option is set to 25 and the top move in a position has a score of 100, no move with a score of less than 75 will be returned.
        - `min_knodes`: The minimum number of kilonodes to search. The minimum number of nodes to search is this value times 1000.
    - Configurations only in `lichess_opening_explorer`:
        - `source`: One of `lichess`, `masters`, or `player`. Whether to use move statistics from masters, lichess players, or a specific player.
        - `player_name`: Used only when `source` is `player`. The username of the player to use for move statistics.
        - `sort`: One of `winrate` or `games_played`. Whether to choose the best move according to the winrate or the games played.
        - `min_games`: The minimum number of times a move must have been played to be considered.
    - Configurations only in `online_egtb`:
        - `max_pieces`: The maximum number of pieces in the current board for which the tablebase will be consulted.
        - `source`: One of `chessdb` or `lichess`. Lichess also has tablebases for atomic and antichess while chessdb only has those for standard.
- `lichess_bot_tbs`: This section gives your bot access to various resources for choosing moves like syzygy and gaviota endgame tablebases. There are two sections that correspond to two different endgame tablebases:
    1. `syzygy`: Get moves from syzygy tablebases. `.*tbw` have to be always provided. Syzygy TBs are generally smaller that gaviota TBs.
    2. `gaviota`: Get moves from gaviota tablebases.
    - Configurations common to all:
        - `enabled`: Whether to use the tablebases at all.
        - `paths`: The paths to the tablebases.
        - `max_pieces`: The maximum number of pieces in the current board for which the tablebase will be consulted.
        - `move_quality`: Choice of `best` or `suggest`.
            - `best`: Choose only the highest scoring move. When using `syzygy`, if `.*tbz` files are not provided, the bot will attempt to get a move using `move_quality` = `suggest`.
            - `suggest`: Let the engine choose between the top moves. The top moves are the all the moves that have the best WDL. Can't be used with XBoard engines.
    - Configurations only in `gaviota`:
        - `min_dtm_to_consider_as_wdl_1`: The minimum DTM to consider as syzygy WDL=1/-1. Setting it to 100 will disable it.

## Offering draw and resigning
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

  Note: If a game reaches 300 moves and no checkmate is delivered on move 300, it is adjudicated as a draw and shows up in the logs as _draw by agreement_ (see [this discussion](https://lichess.org/forum/general-chess-discussion/lichess-300-move-rule-forced-draw) and [this commit](https://github.com/lichess-org/lila/commit/f8921999115878a98431cd722b267281793b7f6f)). That's a lichess-specific behavior which doesn't depend on lichess-bot version or configuration.

## Options for correspondence games
- `correspondence` These options control how the engine behaves during correspondence games.
  - `move_time`: How many seconds to think for each move.
  - `checkin_period`: How often (in seconds) to reconnect to games to check for new moves after disconnecting.
  - `disconnect_time`: How many seconds to wait after the bot makes a move for an opponent to make a move. If no move is made during the wait, disconnect from the game.
  - `ponder`: Whether the bot should ponder during the above waiting period.

## Challenges the BOT should accept
- `challenge`: Control what kind of games for which the bot should accept challenges. All of the following options must be satisfied by a challenge to be accepted.
  - `concurrency`: The maximum number of games to play simultaneously.
  - `sort_by`: Whether to start games by the best rated/titled opponent `"best"` or by first-come-first-serve `"first"`.
  - `preference`: Whether to prioritize human opponents, bot opponents, or treat them equally.
  - `accept_bot`: Whether to accept challenges from other bots.
  - `only_bot`: Whether to only accept challenges from other bots.
  - `max_increment`: The maximum value of time increment.
  - `min_increment`: The minimum value of time increment.
  - `bullet_requires_increment`: Require that bullet game challenges from bots have a non-zero increment. This can be useful if a bot often loses on time in short games due to spotty network connections or other sources of delay.
  - `max_base`: The maximum base time for a game.
  - `min_base`: The minimum base time for a game.
  - `max_days`: The maximum number of days for a correspondence game.
  - `min_days`: The minimum number of days for a correspondence game.
  - `variants`: An indented list of chess variants that the bot can handle.
```yml
  variants:
    - standard
    - horde
    - antichess
    # etc.
```
  - `time_controls`: An indented list of acceptable time control types from `bullet` to `correspondence` (bots are not allowed to play `ultraBullet`).
```yml
  time_controls:
    - bullet
    - blitz
    - rapid
    - classical
    - correspondence
```
  - `modes`: An indented list of acceptable game modes (`rated` and/or `casual`).
```yml
  modes:
    -rated
    -casual
```
  - `block_list`: An indented list of usernames from which the challenges are always declined. If this option is not present, then the list is considered empty.
  - `allow_list`: An indented list of usernames from which challenges are exclusively accepted. A challenge from a user not on this list is declined. If this option is not present or empty, any user's challenge may be accepted.
  - `recent_bot_challenge_age`: Maximum age of a bot challenge to be considered recent in seconds
  - `max_recent_bot_challenges`: Maximum number of recent challenges that can be accepted from the same bot
  - `max_simultaneous_games_per_user`: Maximum number of games that can be played simultaneously with the same user

## Greeting
- `greeting`: Send messages via chat to the bot's opponent. The string `{me}` will be replaced by the bot's lichess account name. The string `{opponent}` will be replaced by the opponent's lichess account name. Any other word between curly brackets will be removed. If you want to put a curly bracket in the message, use two: `{{` or `}}`.
  - `hello`: Message to send to the opponent when the bot makes its first move.
  - `goodbye`: Message to send to the opponent once the game is over.
  - `hello_spectators`: Message to send to the spectators when the bot makes its first move.
  - `goodbye_spectators`: Message to send to the spectators once the game is over.
```yml
  greeting:
    hello: Hi, {opponent}! I'm {me}. Good luck!
    goodbye: Good game!
    hello_spectators: "Hi! I'm {me}. Type !help for a list of commands I can respond to." # Message to send to spectator chat at the start of a game
    goodbye_spectators: "Thanks for watching!" # Message to send to spectator chat at the end of a game
```

## Other options
- `abort_time`: How many seconds to wait before aborting a game due to opponent inaction. This only applies during the first six moves of the game.
- `fake_think_time`: Artificially slow down the engine to simulate a person thinking about a move. The amount of thinking time decreases as the game goes on.
- `rate_limiting_delay`: For extremely fast games, the lichess.org servers may respond with an error if too many moves are played too quickly. This option avoids this problem by pausing for a specified number of milliseconds after submitting a move before making the next move.
- `move_overhead`: To prevent losing on time due to network lag, subtract this many milliseconds from the time to think on each move.
- `max_takebacks_accepted`: Specify the number of times an opponent is allowed to take back their move in a single game.
    - In order for an opponent to be able to request move takebacks, the bot's lichess preferences must be set to accept them.
      1. Sign into the bot's account on the lichess website.
      2. Go to the [`Game behavior`](https://lichess.org/account/preferences/game-behavior) section of the bot's preferences page.
      3. Under `Takebacks (with opponent approval)`, select `Always` or `In casual games only`.
    - Note: bots requesting a move takeback (whether through lichess-bot or through the lichess website) is not supported.
- `quit_after_all_games_finish`: If this is set to `true`, then pressing Ctrl-c to quit will cause lichess-bot to terminate after all in-progress games are finished. No new challenges will be sent or accepted, nor will any correspondence games be checked on. If `false` (the default), lichess-bot will terminate immediately and not wait to finish games in progress. If this value is `true` and you find that you need to quit immediately, press Ctrl-c twice.
- `pgn_directory`: Write a record of every game played in PGN format to files in this directory. Each bot move will be annotated with the bot's calculated score and principal variation. The score is written with a tag of the form `[%eval s,d]`, where `s` is the score in pawns (positive means white has the advantage), and `d` is the depth of the search.
- `pgn_file_grouping`: Determine how games are written to files. There are three options:
    - `game`: Every game record is written to a different file in the `pgn_directory`. The file name is `{White name} vs. {Black name} - {lichess game ID}.pgn`.
    - `opponent`: Game records are written to files named according to the bot's opponent. The file name is `{Bot name} games vs. {Opponent name}.pgn`.
    - `all`: All games are written to the same file. The file name is `{Bot name} games.pgn`.
```yml
  pgn_directory: "game_records"
  pgn_file_grouping: "all"
```

## Challenging other bots
- `matchmaking`: Challenge a random bot.
  - `allow_matchmaking`: Whether to challenge other bots.
  - `allow_during_games`: Whether to issue new challenges while the bot is already playing games. If true, no more than 10 minutes will pass between matchmaking challenges.
  - `challenge_variant`: The variant for the challenges. If set to `random` a variant from the ones enabled in `challenge.variants` will be chosen at random.
  - `challenge_timeout`: The time (in minutes) the bot has to be idle before it creates a challenge.
  - `challenge_initial_time`: A list of initial times (in seconds and to be chosen at random) for the challenges.
  - `challenge_increment`: A list of increments (in seconds and to be chosen at random) for the challenges.
  - `challenge_days`: A list of number of days for a correspondence challenge (to be chosen at random).
  - `opponent_min_rating`: The minimum rating of the opponent bot. The minimum rating in lichess is 600.
  - `opponent_max_rating`: The maximum rating of the opponent bot. The maximum rating in lichess is 4000.
  - `opponent_rating_difference`: The maximum difference between the bot's rating and the opponent bot's rating.
  - `rating_preference`: Whether the bot should prefer challenging high or low rated players, or have no preference.
  - `opponent_allow_tos_violation`: Whether to challenge bots that violated Lichess Terms of Service. Note that even rated games against them will not affect ratings.
  - `challenge_mode`: Possible options are `casual`, `rated` and `random`.
  - `challenge_filter`: Whether and how to prevent challenging a bot after that bot declines a challenge. Options are `none`, `coarse`, and `fine`.
    - `none` does not prevent challenging a bot that declined a challenge.
    - `coarse` will prevent challenging a bot to any type of game after it declines one challenge.
    - `fine` will prevent challenging a bot to the same kind of game that was declined.

    The `challenge_filter` option can be useful if your matchmaking settings result in a lot of declined challenges. The bots that accept challenges will be challenged more often than those that have declined. The filter will remain until lichess-bot quits or the connection with lichess.org is reset.
  - `block_list`: An indented list of usernames of bots that will not be challenged. If this option is not present, then the list is considered empty.
  - `include_challenge_block_list`: If `true`, do not send challenges to the bots listed in the `challenge: block_list`. Default is `false`.
  - `overrides`: Create variations on the matchmaking settings above for more specific circumstances. If there are any subsections under `overrides`, the settings below that will override the settings in the matchmaking section. Any settings that do not appear will be taken from the settings above. <br/> <br/>
  The overrides section must have the following:
    - Name: A unique name must be given for each override. In the example configuration below, `easy_chess960` and `no_pressure_correspondence` are arbitrary strings to name the subsections and they are unique.
    - List of options: A list of options to override. Only the options mentioned will change when making the challenge. The rest will follow the default matchmaking options. In the example settings below, the blank settings for `challenge_initial_time` and `challenge_increment` under `no_pressure_correspondence` have the effect of deleting these settings, meaning that only correspondence games are possible.

    For each matchmaking challenge, the default settings and each override have equal probability of being chosen to create the challenge. For example, in the example configuration below, the default settings, `easy_chess960`, and `no_pressure_correspondence` all have a 1/3 chance of being used to create the next challenge.

    The following configurations cannot be overridden: `allow_matchmaking`, `challenge_timeout`, `challenge_filter` and `block_list`.
  - Additional Points:
    - If there are entries for both real-time (`challenge_initial_time` and/or `challenge_increment`) and correspondence games (`challenge_days`), the challenge will be a random choice between the two.
    - If there are entries for both absolute ratings (`opponent_min_rating` and `opponent_max_rating`) and rating difference (`opponent_rating_difference`), the rating difference takes precedence.

```yml
matchmaking:
  allow_matchmaking: false
  challenge_variant: "random"
  challenge_timeout: 30
  challenge_initial_time:
    - 60
    - 120
  challenge_increment:
    - 1
    - 2
  challenge_days:
     - 1
     - 2
# opponent_min_rating: 600
# opponent_max_rating: 4000
  opponent_rating_difference: 100
  opponent_allow_tos_violation: true
  challenge_mode: "random"
  challenge_filter: none
  overrides:
    easy_chess960:
      challenge_variant: "chess960"
      opponent_min_rating: 400
      opponent_max_rating: 1200
      opponent_rating_difference:
      challenge_mode: casual
    no_pressure_correspondence:
      challenge_initial_time:
      challenge_increment:
      challenge_days:
        - 2
        - 3
      challenge_mode: casual
```

**Next step**: [Upgrade to a BOT account](https://github.com/lichess-bot-devs/lichess-bot/wiki/Upgrade-to-a-BOT-account)

**Previous step**: [Setup the engine](https://github.com/lichess-bot-devs/lichess-bot/wiki/Setup-the-engine)
