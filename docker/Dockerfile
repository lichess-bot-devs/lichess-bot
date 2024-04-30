ARG VARIANT
FROM python:3$VARIANT
MAINTAINER Jean-Marc Astesana <admin@fathzer.com>

ENV LICHESS_BOT_DOCKER="true"
ENV PYTHONDONTWRITEBYTECODE=1

ARG LICHESS_DIR=/lichess-bot
WORKDIR $LICHESS_DIR

COPY . .

RUN python3 -m pip install --no-cache-dir -r requirements.txt

ARG CONF_FOLDER=$LICHESS_DIR/config
RUN ln -s $CONF_FOLDER/config.yml config.yml &&\
    ln -sf $CONF_FOLDER/homemade.py homemade.py &&\
    ln -sf $CONF_FOLDER/extra_game_handlers.py extra_game_handlers.py

CMD python3 lichess-bot.py ${OPTIONS} --disable_auto_logging
