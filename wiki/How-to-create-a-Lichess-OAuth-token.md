# Creating a lichess OAuth token
- Create an account for your bot on [Lichess.org](https://lichess.org/signup).
- **NOTE: If you have previously played games on an existing account, you will not be able to use it as a bot account.**
- Once your account has been created and you are logged in, [create a personal OAuth2 token with the "Play games with the bot API" (`bot:play`) scope](https://lichess.org/account/oauth/token/create?scopes[]=bot:play&description=lichess-bot) selected and a description added.
- A `token` (e.g. `xxxxxxxxxxxxxxxx`) will be displayed. Store this in the `config.yml` file as the `token` field. You can also set the token in the environment variable `$LICHESS_BOT_TOKEN`.
- **NOTE: You won't see this token again on Lichess, so do save it.**

**Next step**: [Setup the engine](https://github.com/lichess-bot-devs/lichess-bot/wiki/Setup-the-engine)

**Previous step**: [Install lichess-bot](https://github.com/lichess-bot-devs/lichess-bot/wiki/How-to-Install)
