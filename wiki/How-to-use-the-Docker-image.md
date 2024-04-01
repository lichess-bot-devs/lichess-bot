First, create a folder where you will put your configuration file, and, possibly, the program that runs your engine (be aware that this program will run inside the container ... in a [Linux Alpine OS](https://www.alpinelinux.org/)).

The configuration file **must** be named ```config.yml```.

You can see an example of this file using the following command: ```docker run --rm --entrypoint=cat lichess-bot-devs/lichess-bot config.yml.default```.  
You can also find documentation [here](https://github.com/lichess-bot-devs/lichess-bot/wiki/Configure-lichess-bot).


Once your configuration file is ready, let say in `/home/me/myEngine` folder, run the following command:
```docker run -d -v /home/me/myEngine:/engine lichess-bot-devs/lichess-bot```

That's all!

If you want to pass some options to the ```lichess-bot.py``` executed in the container, add them to the ```OPTIONS``` environment variable:

```docker run -d -v /home/me/myEngine:/engine --env OPTIONS=-v lichess-bot-devs/lichess-bot```


If you need, you can check the lichess release information using the following command: ```docker run --rm --entrypoint=cat lichess-bot-devs/lichess-bot lib/versioning.yml```

## What if my engine requires some software installation?
You will have to create a new Docker image of your own and install the required software in your `Dockerfile`.
This image is based on [Alpine](https://www.alpinelinux.org/). So, you'll have to install new software using the ```apk``` command.  
For example to install java 17, the docker file would look like:  
```
FROM lichess-bot-devs/lichess-bot

RUN apk add --no-cache openjdk17-jre
```


