## Creating a homemade engine
As an alternative to creating an entire chess engine and implementing one of the communication protocols (`UCI` or `XBoard`), a bot can also be created by writing a single class with a single method. The `search()` method in this new class takes the current board and the game clock as arguments and should return a move based on whatever criteria the coder desires.

Steps to create a homemade bot:

1. Do all the steps in the [How to Install](#how-to-install)
2. In the `config.yml`, change the engine protocol to `homemade`
3. Create a class in `homemade.py` that extends `MinimalEngine`.
4. Create a method called `search()` with an argument `board` that chooses a legal move from the board.
    - There are examples in `homemade.py` to help you get started. These examples show different ways to implement the `search()` method and the proper way to return the chosen move.
5. In the `config.yml`, change the name from `engine_name` to the name of your class
    - In this case, you could change it to:
        `name: "RandomMove"`
