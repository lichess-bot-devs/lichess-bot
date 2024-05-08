#!/bin/sh

ln -s /lichess-bot/config/config.yml lichess-bot/config.yml

if [ -e /lichess-bot/config/homemade.py ]; then
    ln -sf /lichess-bot/config/homemade.py lichess-bot/homemade.py
fi

if [ -e /lichess-bot/config/extra_game_handlers.py ]; then
    ln -sf /lichess-bot/config/extra_game_handlers.py lichess-bot/extra_game_handlers.py
fi
