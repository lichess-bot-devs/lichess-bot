"""
Sample from a trained model
"""
import os
import pickle
from contextlib import nullcontext
import torch
import tiktoken
from nanogpt.model import GPTConfig, GPT

# BASE_DIR = "nanogpt/"
BASE_DIR = "/mnt/data/lichess_bot_eval_part_2/lichess-bot/nanogpt/"


class NanoGptPlayer:
    def __init__(self, model_name: str):
        self.model_name = model_name
        # -----------------------------------------------------------------------------

        init_from = "resume"  # either 'resume' (from an out_dir) or a gpt2 variant (e.g. 'gpt2-xl')
        out_dir = "out"  # ignored if init_from is not 'resume'
        input_dir = "addition"
        test_name = "test.txt"
        start = "12+44="  # or "<|endoftext|>" or etc. Can also specify a file, use as: "FILE:prompt.txt"
        num_samples = 1  # number of samples to draw
        max_new_tokens = 6  # number of tokens generated in each sample
        temperature = 0.01  # 1.0 = no change, < 1.0 = less random, > 1.0 = more random, in predictions
        top_k = 200  # retain only the top_k most likely tokens, clamp others to have 0 probability
        seed = 1337
        # device = "cuda"  # examples: 'cpu', 'cuda', 'cuda:0', 'cuda:1', etc.
        device = "cpu"
        dtype = "float16"  # 'float32' or 'bfloat16' or 'float16'
        compile = False  # use PyTorch 2.0 to compile the model to be faster
        exec(
            # open(f"{BASE_DIR}configurator.py").read() 
            'open(f"{BASE_DIR}configurator.py").read()' # this needs to be a string type according to error
        )  # overrides from command line or config file
        # -----------------------------------------------------------------------------

        torch.manual_seed(seed)
        torch.cuda.manual_seed(seed)
        torch.backends.cuda.matmul.allow_tf32 = True  # allow tf32 on matmul
        torch.backends.cudnn.allow_tf32 = True  # allow tf32 on cudnn
        device_type = (
            "cuda" if "cuda" in device else "cpu"
        )  # for later use in torch.autocast
        ptdtype = {
            "float32": torch.float32,
            "bfloat16": torch.bfloat16,
            "float16": torch.float16,
        }[dtype]
        ctx = (
            nullcontext()
            if device_type == "cpu"
            else torch.amp.autocast(device_type=device_type, dtype=ptdtype)
        )

        # model
        if init_from == "resume":
            # init from a model saved in a specific directory
            # ckpt_path = os.path.join(BASE_DIR, out_dir, self.model_name)
            # ckpt_path = f"nanogpt/out/{self.model_name}"
            # ckpt_path = f"/mnt/data/lichess_bot_eval_part_2/chess-nanoGPT/{self.model_name}"
            ckpt_path = f"{self.model_name}"
            checkpoint = torch.load(ckpt_path, map_location=device)
            # checkpoint = torch.load(ckpt_path, map_location=torch.device('cpu'))
            gptconf = GPTConfig(**checkpoint["model_args"])
            model = GPT(gptconf)
            state_dict = checkpoint["model"]
            unwanted_prefix = "_orig_mod."
            for k, v in list(state_dict.items()):
                if k.startswith(unwanted_prefix):
                    state_dict[k[len(unwanted_prefix) :]] = state_dict.pop(k)
            model.load_state_dict(state_dict)
        elif init_from.startswith("gpt2"):
            # init from a given GPT-2 model
            model = GPT.from_pretrained(init_from, dict(dropout=0.0))

        model.eval()
        model.to(device)
        if compile:
            model = torch.compile(model)  # requires PyTorch 2.0 (optional)

        meta = {
            'vocab_size': 32,
            'itos': {
                0: ' ', 1: '#', 2: '+', 3: '-', 4: '.', 5: '0', 6: '1', 7: '2', 8: '3',
                9: '4', 10: '5', 11: '6', 12: '7', 13: '8', 14: '9', 15: ';', 16: '=',
                17: 'B', 18: 'K', 19: 'N', 20: 'O', 21: 'Q', 22: 'R', 23: 'a', 24: 'b',
                25: 'c', 26: 'd', 27: 'e', 28: 'f', 29: 'g', 30: 'h', 31: 'x'
            },
            'stoi': {
                ' ': 0, '#': 1, '+': 2, '-': 3, '.': 4, '0': 5, '1': 6, '2': 7, '3': 8,
                '4': 9, '5': 10, '6': 11, '7': 12, '8': 13, '9': 14, ';': 15, '=': 16,
                'B': 17, 'K': 18, 'N': 19, 'O': 20, 'Q': 21, 'R': 22, 'a': 23, 'b': 24,
                'c': 25, 'd': 26, 'e': 27, 'f': 28, 'g': 29, 'h': 30, 'x': 31
            }
        }
        # TODO want to make this more general to arbitrary encoder/decoder schemes
        stoi, itos = meta["stoi"], meta["itos"]
        encode = lambda s: [stoi[c] for c in s]
        decode = lambda l: "".join([itos[i] for i in l])

        self.encode = encode
        self.decode = decode
        self.model = model
        self.ctx = ctx
        self.device = device

    def get_nanogpt_response(self, game_state: str, temperature: float) -> str:
        num_samples = 1  # number of samples to draw
        top_k = 200  # retain only the top_k most likely tokens, clamp others to have 0 probability
        max_new_tokens = 10

        game_state = ";" + game_state
        
        # print('MODEL_INPUT:', game_state)

        start_ids = self.encode(game_state)

        x = torch.tensor(start_ids, dtype=torch.long, device=self.device)[None, ...]
        with torch.no_grad():
            with self.ctx:
                for k in range(num_samples):
                    y = self.model.generate(
                        x, max_new_tokens, temperature=temperature, top_k=top_k
                    )

                    model_response = self.decode(y[0].tolist())

        model_response = model_response[len(game_state) :]
        if ";" in model_response:
            model_response = model_response.split(";")[0]
        return model_response

    def get_move_from_response(self, response: str) -> str:
        # Parse the response to get only the first move
        moves = response.split()
        first_move = moves[0]

        return first_move

    def get_move(self, game_state: str, temperature: float) -> str:
        completion = self.get_nanogpt_response(game_state, temperature)
        return self.get_move_from_response(completion)

    def get_config(self) -> dict:
        return {"model": self.model_name}
