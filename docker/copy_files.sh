#!/bin/sh

ln -s /lichess-bot/config/config.yml config.yml

if [ -f /lichess-bot/config/homemade.py ]; then
    ln -sf /lichess-bot/config/homemade.py homemade.py
fi

if [ -f /lichess-bot/config/extra_game_handlers.py ]; then
    ln -sf /lichess-bot/config/extra_game_handlers.py extra_game_handlers.py
fi
