import berserk
import chess
import chess.engine
import time
import logging

# Configuration
TOKEN = "your_api_token_here" # Replace with your Lichess API token
STOCKFISH_PATH = "stockfish" # Adjust if needed

# Logging setup
logging.basicConfig(filename="lichess_bot.log", level=logging.INFO, format="%(asctime)s - %(message)s")

# Lichess API
session = berserk.TokenSession(TOKEN)
client = berserk.Client(session)

# Stockfish engine
engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)

# Time Management Settings
OVERHEAD_BUFFER = 0.15 # Extra time buffer to avoid losing on time
MAX_THINK_TIME = 5 # Never think more than this per move
BULLET_THINK = 0.2
BLITZ_THINK = 0.5
RAPID_THINK = 1.5

# Determine think time per move
def get_time_control(clock):
if not clock:
return RAPID_THINK # Default if no time control
initial, increment = clock["initial"], clock["increment"]
total_time = initial + 40 * increment # Estimate for 40 moves
if total_time < 180: # Bullet
return BULLET_THINK
elif total_time < 600: # Blitz
return BLITZ_THINK
return RAPID_THINK # Rapid/Classical

# Play a game
def play_game(game_id):
logging.info(f"Game started: {game_id}")
game = client.games.export(game_id)
board = chess.Board()
move_time = get_time_control(game["clock"]) - OVERHEAD_BUFFER

while not board.is_game_over():
try:
result = engine.play(board, chess.engine.Limit(time=move_time))
move = result.move.uci()
client.bots.make_move(game_id, move)
board.push(result.move)
logging.info(f"Move: {move} | Time: {move_time}s")
except Exception as e:
logging.error(f"Error making move: {e}")
break

result = board.result()
logging.info(f"Game {game_id} finished with result: {result}")

# Accept only rated challenges
def handle_events():
for event in client.bots.stream_incoming_events():
if event['type'] == 'challenge':
challenge = event['challenge']
if challenge['rated']:
client.bots.accept_challenge(challenge['id'])
logging.info(f"Accepted challenge from {challenge['challenger']['id']}")
else:
client.bots.decline_challenge(challenge['id'])
elif event['type'] == 'gameStart':
play_game(event['game']['id'])

# Start the bot
if __name__ == "__main__":
logging.info("Bot started...")
handle_events()