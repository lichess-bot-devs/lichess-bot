"""Automatically updates the lichess-bot version."""
import yaml
import datetime
import os

# File is part of an implicit namespace package. Add an `__init__.py`.
# ruff: noqa: INP001

with open("lib/versioning.yml") as version_file:
    versioning_info = yaml.safe_load(version_file)

current_version = versioning_info["lichess_bot_version"]

utc_datetime = datetime.datetime.now(datetime.UTC)
new_version = f"{utc_datetime.year}.{utc_datetime.month}.{utc_datetime.day}."
if current_version.startswith(new_version):
    current_version_list = current_version.split(".")
    current_version_list[-1] = str(int(current_version_list[-1]) + 1)
    new_version = ".".join(current_version_list)
else:
    new_version += "1"

versioning_info["lichess_bot_version"] = new_version

with open("lib/versioning.yml", "w") as version_file:
    yaml.dump(versioning_info, version_file, sort_keys=False)

with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
    print(f"new_version={new_version}", file=fh)
