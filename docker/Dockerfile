FROM python:3-alpine
MAINTAINER Jean-Marc Astesana <admin@fathzer.com>

WORKDIR ./lichessbot

COPY . .

RUN python3 -m pip install --no-cache-dir -r requirements.txt

CMD python3 lichess-bot.py ${OPTIONS} --config /engine/config.yml
