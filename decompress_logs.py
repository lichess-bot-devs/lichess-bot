"""Decompress logs."""
import gzip
import os


def decompress_logs(directory: str = "./lichess_bot_weekly_logs/", only_file: str = "") -> None:
    """Decompress logs."""
    for filename in os.listdir(directory):
        path = os.path.join(directory, filename)
        if path.endswith(".compressed_log") and only_file in path:
            decompressed_path = f"{path[:-15]}.decompressed_log"
            with gzip.open(path) as file:
                contents = file.read().decode()
            with open(decompressed_path, "w") as file:
                file.write(contents)


if __name__ == "__main__":
    decompress_logs()
