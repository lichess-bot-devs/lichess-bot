ARG VARIANT
FROM python:3$VARIANT
MAINTAINER Lichess Bot Devs <lichess.bot.devs@gmail.com>

ENV LICHESS_BOT_DOCKER="true"
ENV PYTHONDONTWRITEBYTECODE=1

ARG LICHESS_DIR=/lichess-bot
WORKDIR $LICHESS_DIR

COPY . .

RUN python3 -m pip install --no-cache-dir -r requirements.txt

ARG CONF_FOLDER=$LICHESS_DIR/config

RUN chmod +x docker/copy_files.sh

CMD docker/copy_files.sh && python3 lichess-bot.py ${OPTIONS} --disable_auto_logging
