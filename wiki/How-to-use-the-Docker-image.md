First, create a folder where you will put your configuration file, and, possibly, the program that runs your engine (be aware that this program will run inside the container ... in a [Linux Alpine OS](https://www.alpinelinux.org/)).

The configuration file **must** be named ```config.yml```.

You can see an example of this file using the following command: ```docker run --rm --entrypoint=cat lichess-bot-devs/lichess-bot config.yml.default```.  
You can also find documentation [here](https://github.com/lichess-bot-devs/lichess-bot/wiki/Configure-lichess-bot).


Once your configuration file is ready, let's say in `/home/me/myEngine` folder, run the following command:
```docker run -d -v /home/me/myEngine:/engine lichess-bot-devs/lichess-bot```

That's all!

If you want to pass some options to the ```lichess-bot.py``` executed in the container, add them to the ```OPTIONS``` environment variable:
```docker run -d -v /home/me/myEngine:/engine --env OPTIONS=-v lichess-bot-devs/lichess-bot```

If you need to, you can check the lichess release information using the following command: ```docker run --rm --entrypoint=cat lichess-bot-devs/lichess-bot lib/versioning.yml```


## Image variants
The `lichess-bot` images come in two flavors, each designed for a specific use case.
### lichess-bot:\<version\>
This is the defacto image. It is based on the [`python:3`](https://hub.docker.com/_/python) image.
If you are unsure about what your needs are, you probably want to use this one.

### lichess-bot:\<version\>-alpine
This image is based on the popular Alpine Linux project, available in the alpine official image. Alpine Linux is much smaller than most distribution base images, and thus leads to a much slimmer image than the default one (70MB instead of 1GB).

This variant is useful when final image size being as small as possible is your primary concern. The main caveat to note is that it does use musl libc instead of glibc and friends, so software will often run into issues depending on the depth of their libc requirements/assumptions. For instance, running [Stockfish](https://stockfishchess.org/) on this image requires extra libraries installation.


## What if my engine requires some software installation?
You will have to create a new Docker image of your own and install the required software in your `Dockerfile`.
For example to install java 17, the docker file would look like:  
```
FROM lichess-bot-devs/lichess-bot:alpine

RUN apk add --no-cache openjdk17-jre
```
Please note that, as `lichess-bot:alpine` image is based on [Alpine](https://www.alpinelinux.org/). So, you'll have to install new software using the ```apk``` command.  


