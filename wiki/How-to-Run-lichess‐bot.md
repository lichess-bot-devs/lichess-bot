## Running lichess-bot
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

If you want to specify a different config file, add the `--config` along with a file name:
```
python3 lichess-bot.py --config config2.yml
```

### Running as a service
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

## Quitting
- Press `CTRL+C`.
- If `quit_after_all_games_finish` is set to `true` in your config file, lichess-bot will wait for all games to exit. Otherwise, all games will exit immediately.
- It may take several seconds for lichess-bot to quit once all games have exited.

**Previous step**: [Upgrade to a BOT account](https://github.com/lichess-bot-devs/lichess-bot/wiki/Upgrade-to-a-BOT-account)
