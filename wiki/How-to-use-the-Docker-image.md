# How to launch your bot
## Download the docker image
The images are available through [Docker hub](https://hub.docker.com/r/lichessbotdevs/lichess-bot) and [Github container registry](https://github.com/lichess-bot-devs/lichess-bot/pkgs/container/lichess-bot).
Run `docker pull lichessbotdevs/lichess-bot` to download from docker hub, or run `docker pull ghcr.io/lichess-bot-devs/lichess-bot` if you want to download it from the Github container registry.

**NOTE**: On Docker hub, the organization name is `lichessbotdevs` (without hyphens) while on the Github container registry it is `lichess-bot-devs`. The package name is in both cases `lichess-bot` (with hyphens).

In the steps below replace `lichessbotdevs` with `ghcr.io/lichess-bot-devs` if you downloaded the image through the Github container registry.

## Prepare the deployment
Create a folder where you will put your configuration file, the UCI/XBoard program that runs your engine (be aware that this program will run inside the container ... in a Linux OS) or your own [`homemade.py`](https://github.com/lichess-bot-devs/lichess-bot/wiki/Create-a-homemade-engine) and, if required, your own [`extra_game_handlers.py`](https://github.com/lichess-bot-devs/lichess-bot/wiki/Extra-customizations).

The configuration file **must** be named `config.yml`.

You can see an example of this file using the following command:  
```docker run --rm --entrypoint=cat lichessbotdevs/lichess-bot config.yml.default```.

You can also find documentation [here](https://github.com/lichess-bot-devs/lichess-bot/wiki/Configure-lichess-bot).

## Run the bot

Once your configuration files are ready, let's say in `/home/me/myEngine` folder, run the following command:  
```docker run -d -v /home/me/myEngine:/lichess-bot/config --name myBot lichessbotdevs/lichess-bot```

**NOTE**: Prefer using absolute paths over relative paths, as relative ones may cause problems.

That's all!

### Warning:
- Make sure you've set the `dir` and `working_dir` attributes of your `config.yml` to the right path (remember the engine runs in the container's OS, so the path should start with `/lichess-bot/config/`).
- **If you've configured a folder to save pgn files** using [`pgn_directory`](https://github.com/lichess-bot-devs/lichess-bot/wiki/Configure-lichess-bot#other-options) that is not in `/lichess-bot/config` directory, always mount a volume to that folder. Without that, your saved games will remain unreachable from the outside of the container, and storing a lot of games in the container's file system could result in disk saturation.
- The container uses the standard docker logging system and the bot is always launched with the `--disable_auto_logging` option.
  Use the `docker logs myBot` [command](https://docs.docker.com/reference/cli/docker/container/logs/) to access to the bot logs.

## Stop and delete the bot
Use the standard commands.  
If you used the command from the [Run chapter](#run-the-bot) above: ```docker stop myBot``` and ```docker rm myBot```

# Image variants

The `lichess-bot` images come in two flavors, each designed for a specific use case.  

## lichess-bot:\<version\>
This is the defacto image. It is based on the [`python:3`](https://hub.docker.com/_/python) image.
If you are unsure about what your needs are, you probably want to use this one.

To download the latest version use `lichess-bot:latest`.

## lichess-bot:\<version\>-alpine
This image is based on the popular Alpine Linux project, available in the alpine official image. Alpine Linux is much smaller than most distribution base images, and thus leads to a much slimmer image than the default one (80MB instead of 1GB).

This variant is useful when final image size being as small as possible is your primary concern. The main caveat to note is that it does use musl libc instead of glibc and friends, so software will often run into issues depending on the depth of their libc requirements/assumptions. For instance, running [Stockfish](https://stockfishchess.org/) on this image requires extra libraries installation.

To download the latest version use `lichess-bot:alpine`.

# Some tips

## What if my engine requires some software installation?
You will have to create a new Docker image of your own and install the required software in your `Dockerfile`.
For example to install java 17, the docker file would look like:  
```
FROM lichessbotdevs/lichess-bot:alpine

RUN apk add --no-cache openjdk17-jre
```
Please note that, as `lichess-bot:alpine` image is based on [Alpine](https://www.alpinelinux.org/), you'll have to install new software using the ```apk``` command.

## What if I want to add options to ```lichess-bot.py```?

If you want to pass some options to the ```lichess-bot.py``` executed in the container, add them in the ```OPTIONS``` environment variable.  
For instance, to launch the bot in verbose mode, run the command:  
```docker run -d -v /home/me/myEngine:/lichess-bot/config --env OPTIONS=-v lichessbotdevs/lichess-bot```

## How to know which release of lichess-bot is running?
Use the following command: ```docker run --rm --entrypoint=cat lichessbotdevs/lichess-bot lib/versioning.yml```
