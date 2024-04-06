"""
Some example classes for people who want to create a homemade bot.

With these classes, bot makers will not have to implement the UCI or XBoard interfaces themselves.
"""

from __future__ import annotations
import re
import chess
from chess.engine import PlayResult
import logging
from homemade import ExampleEngine
from lib.engine_wrapper import FillerEngine, check_for_draw_offer, get_book_move, get_egtb_move, get_online_move, move_time
from nanogpt.nanogpt_module import NanoGptPlayer
import chess.engine
import chess.polyglot
import chess.syzygy
import chess.gaviota
import logging
import datetime
import time
import test_bot.lichess
from lib import config, model, lichess
from lib.timer import Timer, to_seconds
from typing import Any, Optional, Union
OPTIONS_TYPE = dict[str, Any]
MOVE_INFO_TYPE = dict[str, Any]
COMMANDS_TYPE = list[str]
LICHESS_EGTB_MOVE = dict[str, Any]
CHESSDB_EGTB_MOVE = dict[str, Any]
MOVE = Union[chess.engine.PlayResult, list[chess.Move]]
LICHESS_TYPE = Union[lichess.Lichess, test_bot.lichess.Lichess]

from dataclasses import dataclass


@dataclass
class LegalMoveResponse:
    move_san: Optional[str] = None
    move_uci: Optional[chess.Move] = None
    attempts: int = 0
    is_resignation: bool = False
    is_illegal_move: bool = False

# Use this logger variable to print messages to the console or log files.
# logger.info("message") will always print "message" to the console or log file.
# logger.debug("message") will only print "message" if verbose logging is enabled.
logger = logging.getLogger(__name__)


# Return is (move_san, move_uci, attempts, is_resignation, is_illegal_move)
def get_legal_move(
    player: NanoGptPlayer,
    board: chess.Board,
    game_state: str,
    player_one: bool = False,
    max_attempts: int = 5,
# ) -> LegalMoveResponse:
) -> PlayResult:
    """Request a move from the player and ensure it's legal."""
    move_san = None
    move_uci = None


    for attempt in range(max_attempts):
        move_san = player.get_move(game_state, 0.5)
        # player.get_move(
        #     board, game_state, min(((attempt / max_attempts) * 1) + 0.001, temperature)
        # )

        # Sometimes when GPT thinks it's the end of the game, it will just output the result
        # Like "1-0". If so, this really isn't an illegal move, so we'll add a check for that.
        if move_san is not None:
            if move_san == "1-0" or move_san == "0-1" or move_san == "1/2-1/2":
                print(f"{move_san}, player has resigned")
                # TODO
                return PlayResult("", "") #!
                # return PlayResult("", None) #!
                # return LegalMoveResponse(
                #     move_san=None,
                #     move_uci=None,
                #     attempts=attempt,
                #     is_resignation=True,
                # )

        try:
            # just_move_san = move_san
            # if "." in just_move_san:
            #     just_move_san = just_move_san.split(".")[1]
            # move_uci = board.parse_san(just_move_san)
            move_uci = board.parse_san(move_san)
            return PlayResult(move_uci, None)            
            
        except Exception as e:
            print(f"Error parsing move {move_san}: {e}")
            # raise e
            # check if player is gpt-3.5-turbo-instruct
            # only recording errors for gpt-3.5-turbo-instruct because it's errors are so rare
            # if player.get_config()["model"] == "gpt-3.5-turbo-instruct":
            #     with open("gpt-3.5-turbo-instruct-illegal-moves.txt", "a") as f:
            #         f.write(f"{game_state}\n{move_san}\n")
            continue

    if move_uci is None:
        raise Exception('Failed to find legal move')
    
    
    # if move_uci in board.legal_moves:
    #     if player_one == False:
    #         if not move_san.startswith(" "):
    #             move_san = " " + move_san
    #     else:
    #         if move_san.startswith(" "):
    #             move_san = move_san[1:]
    #     return LegalMoveResponse(move_san, move_uci, attempt)
    # print(f"Illegal move: {move_san}")

    # # If we reach here, the player has made illegal moves for all attempts.
    # print(f"{player} provided illegal moves for {max_attempts} attempts.")
    # return LegalMoveResponse(
    #     move_san=None, move_uci=None, attempts=max_attempts, is_illegal_move=True
    # )



class NanoGPTEngine(ExampleEngine):
    def __init__(self, model_name: str, commands: COMMANDS_TYPE, options: OPTIONS_TYPE, stderr: Optional[int],
                 draw_or_resign: config.Configuration, game: Optional[model.Game] = None, name: Optional[str] = None, temperature: float = 0.,
                 **popen_args: str):
        self.player = NanoGptPlayer(model_name = model_name)
        self.temperature = temperature
        # super().__init__(options, draw_or_resign) # there are no options or draw_or_resign values in the config.yml file

        self.engine_name = self.__class__.__name__ if name is None else name

        self.engine = FillerEngine(self, name=self.engine_name)

        self.game_state = ''
        
        self.prior_board = None
        
    def search(self, board: chess.Board) -> PlayResult: 
        # print(board.fullmove_number)
        # print('\n\n\n', '*********', '\n\n\n')

        # ## WHITE CODE
        # if board.fullmove_number == 1:
        #     self.prior_board = chess.Board()            
        #     self.game_state = f"1."
        # else: # this appends a move_uci, which looks like d7d5 instead of just d5.
        #     self.game_state = f"{self.game_state}{self.prior_board.san(board.move_stack[-2])}"
        #     self.prior_board.push(board.move_stack[-2])
        #     self.game_state += f" {self.prior_board.san(board.move_stack[-1])} {board.fullmove_number}."
        #     self.prior_board.push(board.move_stack[-1])
        
        # ## BLACK CODE
        # if board.fullmove_number == 1:
        #     self.prior_board = chess.Board()            
        #     self.game_state = f"1.{self.prior_board.san(board.move_stack[-1])} "
        #     self.prior_board.push(board.move_stack[-1])
        # else: # this appends a move_uci, which looks like d7d5 instead of just d5.
        #     self.game_state = f"{self.game_state}{self.prior_board.san(board.move_stack[-2])}"
        #     self.prior_board.push(board.move_stack[-2])
        #     self.game_state += f" {board.fullmove_number}.{self.prior_board.san(board.move_stack[-1])} "
        #     self.prior_board.push(board.move_stack[-1])
            
            
        is_black =  board.turn == chess.BLACK

        if board.fullmove_number == 1:
            self.prior_board = chess.Board()            
            self.game_state = f"1.{self.prior_board.san(board.move_stack[-1]) + ' ' if is_black else ''}"
        else:
            self.game_state = f"{self.game_state}{self.prior_board.san(board.move_stack[-2])}"
            self.prior_board.push(board.move_stack[-2])
            if is_black:
                self.game_state += f" {board.fullmove_number}.{self.prior_board.san(board.move_stack[-1])} "
            else:
                self.game_state += f" {self.prior_board.san(board.move_stack[-1])} {board.fullmove_number}."
            self.prior_board.push(board.move_stack[-1])
            
            
            
        # append board.move_stack[-1]
        # board.ply() for the player num
        # print(f'GAME_STATE @ {board.fullmove_number}', game_state)
        return get_legal_move(self.player, board, self.game_state)
        # return PlayResult(self.player.get_move(board, game_state, self.temperature).from_uci(), None)
        
        # if not player_one:
            #     # Add next full move number and the move of the white player
            #     # game_state += f" {board.fullmove_number}.{board.move_stack[-1].__str__()}"
            #     game_state += f" {board.fullmove_number}."
    
        # result = get_legal_move(self.player, board, game_state, player_one)
        # illegal_moves = result.attempts
        # move_san = result.move_san
        # move_uci = result.move_uci
        # resignation = result.is_resignation
        # failed_to_find_legal_move = result.is_illegal_move
        
        # if resignation:
        #     print(f"{self.player} resigned with result: {board.result()}")
        # elif failed_to_find_legal_move:
        #     print(f"Game over: 5 consecutive illegal moves from {self.player}")
        # elif move_san is None or move_uci is None:
        #     print(f"Game over: {self.player} failed to find a legal move")
        # else:
        #     board.push(move_uci)
        #     # if player_one:
        #     #     game_state += f"{board.fullmove_number}.{move_san}
        #     # else:
        #     game_state += move_san 
                
        #     self.game_state = game_state
        #     print(move_san, end=" ")
            
        # return PlayResult(move_uci, None)
    
    
    def play_move(self,
                  board: chess.Board,
                  game: model.Game,
                  li: LICHESS_TYPE,
                  setup_timer: Timer,
                  move_overhead: datetime.timedelta,
                  can_ponder: bool,
                  is_correspondence: bool,
                  correspondence_move_time: datetime.timedelta,
                  engine_cfg: config.Configuration,
                  min_time: datetime.timedelta) -> None:
        """
        Play a move.

        :param board: The current position.
        :param game: The game that the bot is playing.
        :param li: Provides communication with lichess.org.
        :param start_time: The time that the bot received the move.
        :param move_overhead: The time it takes to communicate between the engine and lichess.org.
        :param can_ponder: Whether the engine is allowed to ponder.
        :param is_correspondence: Whether this is a correspondence or unlimited game.
        :param correspondence_move_time: The time the engine will think if `is_correspondence` is true.
        :param engine_cfg: Options for external moves (e.g. from an opening book), and for engine resignation and draw offers.
        :param min_time: Minimum time to spend, in seconds.
        :return: The move to play.
        """
        polyglot_cfg = engine_cfg.polyglot
        online_moves_cfg = engine_cfg.online_moves
        draw_or_resign_cfg = engine_cfg.draw_or_resign
        lichess_bot_tbs = engine_cfg.lichess_bot_tbs

        best_move: MOVE
        best_move = get_book_move(board, game, polyglot_cfg)

        if best_move.move is None:
            best_move = get_egtb_move(board,
                                      game,
                                      lichess_bot_tbs,
                                      draw_or_resign_cfg)

        if not isinstance(best_move, list) and best_move.move is None:
            best_move = get_online_move(li,
                                        board,
                                        game,
                                        online_moves_cfg,
                                        draw_or_resign_cfg)

        if isinstance(best_move, list) or best_move.move is None:
            draw_offered = check_for_draw_offer(game)

            time_limit, can_ponder = move_time(board, game, can_ponder,
                                               setup_timer, move_overhead,
                                               is_correspondence, correspondence_move_time)

            try:                
                best_move = self.search(board) # this is a guess to ge the pgn state of the current game.
                
                # # uses str() to transform the dictionary that describes the game state to a string
                # # best_move = self.search(board, str(game.state["state"])) # this is kinda bs because the state of the game probably does not correspond to the 
                # # print("=====Search Called=====\n")
                
                # # game_state = li.get_game_pgn(game.id)
                # # # game_state ='[Event "Rated Blitz game"]\n[Site "https://lichess.org/73DfNVss"]\n[Date "2024.04.04"]\n[White "maia9"]\n[Black "project-eval-bot"]\n[Result "*"]\n[UTCDate "2024.04.04"]\n[UTCTime "20:58:06"]\n[WhiteElo "1481"]\n[BlackElo "2013"]\n[WhiteTitle "BOT"]\n[BlackTitle "BOT"]\n[Variant "Standard"]\n[TimeControl "180+1"]\n[ECO "A40"]\n[Opening "Queen\'s Pawn Game"]\n[Termination "Unterminated"]\n\n1. d4 { [%clk 0:03:00] } *\n\n\n'
                # # '[Event "Rated Blitz game"]\n[Site "https://lichess.org/bFlyeAz3"]\n[Date "2024.04.06"]\n[White "maia9"]\n[Black "project-eval-bot"]\n[Result "*"]\n[UTCDate "2024.04.06"]\n[UTCTime "10:49:56"]\n[WhiteElo "1556"]\n[BlackElo "1483"]\n[WhiteTitle "BOT"]\n[BlackTitle "BOT"]\n[Variant "Standard"]\n[TimeControl "180+1"]\n[ECO "A40"]\n[Opening "Queen\'s Pawn Game"]\n[Termination "Abandoned"]\n\n1. d4 { [%clk 0:03:00] } *\n\n\n'
                # # pattern1 = r'\[White "(.*?)"\]\n\[Black "(.*?)"\]'
                # # game_desc_substring = re.search(pattern1, game_state)
                # # game_state = game_desc_substring.group()
                
                # # if board.fullmove_number != 1 and self.game_state != '': # sometimes it thinks it is the seond move  
                # game_state = self.game_state
                # player_one = False
                # # pattern1 = r'\[White "(.*?)"\]\n\[Black "(.*?)"\]'
                # # game_desc_substring = re.search(pattern1, li.get_game_pgn(game.id))
                # # white_player = game_desc_substring.group(1)
                # # black_player = game_desc_substring.group(2)
                
                # prior_board = chess.Board()
                
                
                # # if black_player == "project-eval-bot": #if we are Black
                # if board.fullmove_number == 1:
                #     game_state = li.get_game_pgn(game.id)
                #     # game_state ='[Event "Rated Blitz game"]\n[Site "https://lichess.org/73DfNVss"]\n[Date "2024.04.04"]\n[White "maia9"]\n[Black "project-eval-bot"]\n[Result "*"]\n[UTCDate "2024.04.04"]\n[UTCTime "20:58:06"]\n[WhiteElo "1481"]\n[BlackElo "2013"]\n[WhiteTitle "BOT"]\n[BlackTitle "BOT"]\n[Variant "Standard"]\n[TimeControl "180+1"]\n[ECO "A40"]\n[Opening "Queen\'s Pawn Game"]\n[Termination "Unterminated"]\n\n1. d4 { [%clk 0:03:00] } *\n\n\n'
                #     pattern1 = r'\[White "(.*?)"\]\n\[Black "(.*?)"\]'
                #     # pattern2 = r'\n\n(.*?) \{'
                #     game_desc_substring = re.search(pattern1, game_state)
                #     # moves_substring = re.search(pattern2, game_state)
                #     # moves_so_far = moves_substring.group().strip()
                #     # moves_so_far = moves_substring.group().replace(" ", "")
                #     # print(f"moves so far: {moves_so_far}")
                #     print("Move Stack Length: ", len(board.move_stack))
                #     game_state = f"{game_desc_substring.group()}\n\n1.{prior_board.san(board.move_stack[-1])} "
                #     prior_board.push(board.move_stack[-1])
                #     # game_state = game_desc_substring.group() + moves_so_far[: -1] # remove the tailing {
                #     player_one = False
                        
                # # elif white_player == "project-eval-bot": # if we are White
                # #     if board.fullmove_number == 1:
                # #         game_state = li.get_game_pgn(game.id)
                # #         # game_state ='[Event "Rated Blitz game"]\n[Site "https://lichess.org/73DfNVss"]\n[Date "2024.04.04"]\n[White "maia9"]\n[Black "project-eval-bot"]\n[Result "*"]\n[UTCDate "2024.04.04"]\n[UTCTime "20:58:06"]\n[WhiteElo "1481"]\n[BlackElo "2013"]\n[WhiteTitle "BOT"]\n[BlackTitle "BOT"]\n[Variant "Standard"]\n[TimeControl "180+1"]\n[ECO "A40"]\n[Opening "Queen\'s Pawn Game"]\n[Termination "Unterminated"]\n\n1. d4 { [%clk 0:03:00] } *\n\n\n'
                # #         pattern1 = r'\[White "(.*?)"\]\n\[Black "(.*?)"\]'
                # #         game_desc_substring = re.search(pattern1, game_state)
                # #         game_state = game_desc_substring.group() + '\n\n'
                # #         player_one = True
                # # else:
                #     # raise Exception('Failed to determine project-eval-bot as either player')
                    
                # best_move = self.search(prior_board, board, game_state, player_one) # this is a guess to ge the pgn state of the current game.
                    
                # # if not moves_substring:
                # #     game_state = game_desc_substring.group() + '\n\n'
                # # else:
                # #     game_state = game_state
                # #     game_state = game_desc_substring.group() + moves_substring.group()[: -1] # remove the tailing {
                # # best_move = self.search(board, game_state) # this is a guess to ge the pgn state of the current game.
                
            except chess.engine.EngineError as error:
                BadMove = (chess.IllegalMoveError, chess.InvalidMoveError)
                if any(isinstance(e, BadMove) for e in error.args):
                    logger.error("Ending game due to bot attempting an illegal move.")
                    game_ender = li.abort if game.is_abortable() else li.resign
                    game_ender(game.id)
                raise

        # Heed min_time
        elapsed = setup_timer.time_since_reset()
        if elapsed < min_time:
            time.sleep(to_seconds(min_time - elapsed))

        # self.add_comment(best_move, board) # my nanogpt doesn't have a comment function I guess
        # self.print_stats()
        if best_move.resigned and len(board.move_stack) >= 2:
            li.resign(game.id)
        else:
            li.make_move(game.id, best_move)
