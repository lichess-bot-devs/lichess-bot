"""Automatically updates the lichess-bot version."""
import yaml
import datetime

with open("versioning.yml") as version_file:
    versioning_info = yaml.safe_load(version_file)

current_version = versioning_info["lichess_bot_version"]

utc_datetime = datetime.datetime.utcnow()
new_version = f"{utc_datetime.year}.{utc_datetime.month}.{utc_datetime.day}."
if current_version.startswith(new_version):
    current_version_list = current_version.split(".")
    current_version_list[-1] = str(int(current_version_list[-1]) + 1)
    new_version = ".".join(current_version_list)
else:
    new_version += "1"

versioning_info["lichess_bot_version"] = new_version

with open("versioning.yml", "w") as version_file:
    yaml.dump(versioning_info, version_file, sort_keys=False)
