ARG VARIANT
FROM python:3$VARIANT
MAINTAINER Lichess Bot Devs <lichess.bot.devs@gmail.com>

ENV LICHESS_BOT_DOCKER="true"
ENV PYTHONDONTWRITEBYTECODE=1

ARG LICHESS_DIR=/lichess-bot
WORKDIR $LICHESS_DIR

COPY . .

RUN python3 -m pip install --no-cache-dir -r requirements.txt

RUN chmod +x docker/copy_files.sh && ln -s $LICHESS_DIR/config/config.yml config.yml

CMD docker/copy_files.sh && python3 lichess-bot.py ${OPTIONS} --disable_auto_logging
