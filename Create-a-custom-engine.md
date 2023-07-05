## Creating a custom engine
As an alternative to creating an entire chess engine and implementing one of the communication protocols (`UCI` or `XBoard`), a bot can also be created by writing a single class with a single method. The `search()` method in this new class takes the current board and the game clock as arguments and should return a move based on whatever criteria the coder desires.

Steps to create a homemade bot:

1. Do all the steps in the [How to Install](#how-to-install)
2. In the `config.yml`, change the engine protocol to `homemade`
3. Create a class in some file that extends `MinimalEngine` (in `strategies.py`).
    - Look at the `strategies.py` file to see some examples.
    - If you don't know what to implement, look at the `EngineWrapper` or `UCIEngine` class.
        - You don't have to create your own engine, even though it's an "EngineWrapper" class.<br>
The examples just implement `search`.
4. In the `config.yml`, change the name from `engine_name` to the name of your class
    - In this case, you could change it to:

        `name: "RandomMove"`