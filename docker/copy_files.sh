#!/bin/sh

if [ -e /lichess-bot/config/homemade.py ]; then
    ln -sf /lichess-bot/config/homemade.py /lichess-bot/
fi

if [ -e /lichess-bot/config/extra_game_handlers.py ]; then
    ln -sf /lichess-bot/config/extra_game_handlers.py /lichess-bot/
fi
