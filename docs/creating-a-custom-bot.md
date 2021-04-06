# Creating a custom bot

If you want to create your own bot... then do the following:

1. Do all the steps in the `README`
2. In the `config.yml`, change the engine protocol to `homemade`
3. Create a class in some file that extends `EngineWrapper` (in `engine_wrapper.py`)
    - For example, you could implement a random_mover_bot like this: 
      ```python
      import random
      from engine_wrapper import EngineWrapper
      class RandomMover(EngineWrapper):
          def first_search(self, board, movetime, ponder):
              return self.search(board, movetime, ponder)

          def search(self, board, _time_limit, _ponder):
              return random.choice(board.legal_moves)
      ```
   - If you don't know what to implement, look at the `EngineWrapper` or `UCIEngine` class.
4. In `engine_wrapper.py` change `getHomemadeEngine()` to return your class
    - For example, you could change it to: 
      ```python
      # This function is at the bottom of the file
      def getHomemadeEngine():
         import yourclass
         return yourclass
      ```
