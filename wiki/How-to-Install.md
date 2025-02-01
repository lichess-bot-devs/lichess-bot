### Linux
- **NOTE: Only Python 3.9 or later is supported!**
- Download the repo into lichess-bot directory.
- Navigate to the directory in cmd/Terminal: `cd lichess-bot`.
- Install dependencies: `apt install python3 python3-pip python3-virtualenv python3-venv`.
  - In non-Ubuntu linux distros, replace `apt` with the correct package manager (`pacman` in Arch, `dnf` in Fedora, etc.), package name, and installation command.
- Run the following commands to set up a virtual environment:
```
python3 -m venv venv # If this fails you probably need to add Python3 to your PATH.
virtualenv venv -p python3
source ./venv/bin/activate
python3 -m pip install -r requirements.txt
```
- Copy `config.yml.default` to `config.yml`.

**Next step**: [Create a Lichess OAuth token](https://github.com/lichess-bot-devs/lichess-bot/wiki/How-to-create-a-Lichess-OAuth-token)

### Mac/BSD
- **NOTE: Only Python 3.9 or later is supported!**
- Install Python and other dependencies using the [homebrew package manager](https://brew.sh/):
  - ` brew install python3 virtualenv # Net-/FreeBSD users might want to install: git, python311, py311-pip and py311-virtualenv.`
- Download the repo into lichess-bot directory.
- Navigate to the directory in cmd/Terminal: `cd lichess-bot`.
```
python3 -m venv venv # If this fails you probably need to add Python3 to your PATH.
virtualenv venv -p python3
. venv/bin/activate
python3 -m pip install -r requirements.txt
```
- Copy `config.yml.default` to `config.yml`.

**Next step**: [Create a Lichess OAuth token](https://github.com/lichess-bot-devs/lichess-bot/wiki/How-to-create-a-Lichess-OAuth-token)

### Windows
- **NOTE: Only Python 3.9 or later is supported!**
- If needed, install Python:
  - [Download Python here](https://www.python.org/downloads/).
  - When installing, enable "add Python to PATH".
  - If the Python version is at least 3.10, a default local install works.
  - If the Python version is 3.9, choose "Custom installation", keep the defaults on the Optional Features page, and choose "Install for all users" in the Advanced Options page.
- Start Terminal, PowerShell, cmd, or your preferred command prompt.
- Upgrade pip: `py -m pip install --upgrade pip`.
- Download the repo into lichess-bot directory.
- Navigate to the directory: `cd [folder's address]` (for example, `cd C:\Users\username\repos\lichess-bot`).
- Install virtualenv: `py -m pip install virtualenv`.
- Setup virtualenv:
```
py -m venv venv # If this fails you probably need to add Python3 to your PATH.
venv\Scripts\activate
pip install -r requirements.txt
```
PowerShell note: If the `activate` command does not work in PowerShell, execute `Set-ExecutionPolicy RemoteSigned` first and choose `Y` there (you may need to run Powershell as administrator). After you execute the script, change execution policy back with `Set-ExecutionPolicy Restricted` and pressing `Y`.
- Copy `config.yml.default` to `config.yml`.

**Next step**: [Create a Lichess OAuth token](https://github.com/lichess-bot-devs/lichess-bot/wiki/How-to-create-a-Lichess-OAuth-token)

### Docker
If you have a [Docker](https://www.docker.com/) host, you can use the ```lichess-bot-devs/lichess-bot``` [image in DockerHub](https://hub.docker.com/r/lichessbotdevs/lichess-bot).
It requires a folder where you have to copy `config.yml.default` to `config.yml`.

See [Running with Docker](https://github.com/lichess-bot-devs/lichess-bot/wiki/How-to-use-the-Docker-image) once you've created the OAuth token and setup the engine.

**Next step**: [Create a Lichess OAuth token](https://github.com/lichess-bot-devs/lichess-bot/wiki/How-to-create-a-Lichess-OAuth-token)
