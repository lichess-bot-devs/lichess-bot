# Setup the engine
## For all engines
Within the file `config.yml`:
- Enter the directory containing the engine executable in the `engine: dir` field.
- Enter the executable name in the `engine: name` field (In Windows you may need to type a name with ".exe", like "lczero.exe")
- If you want the engine to run in a different directory (e.g., if the engine needs to read or write files at a certain location), enter that directory in the `engine: working_dir` field.
  - If this field is blank or missing, the current directory will be used.
  - IMPORTANT NOTE: If this field is used, the running engine will look for files and directories (Syzygy tablebases, for example) relative to this path, not the directory where lichess-bot was launched. Files and folders specified with absolute paths are unaffected.

As an optional convenience, there is a folder named `engines` within the lichess-bot folder where you can copy your engine and all the files it needs. This is the default executable location in the `config.yml.default` file.

## For Leela Chess Zero
### LeelaChessZero: Mac/Linux
- Download the weights for the id you want to play from [here](https://lczero.org/play/networks/bestnets/).
- Extract the weights from the zip archive and rename it to `latest.txt`.
- For Mac/Linux, build the lczero binary yourself following [LeelaChessZero/lc0/README](https://github.com/LeelaChessZero/lc0/blob/master/README.md).
- Copy both the files into the `engine.dir` directory.
- Change the `engine.name` and `engine.engine_options.weights` keys in `config.yml` file to `lczero` and `weights.pb.gz`.
- You can specify the number of `engine.uci_options.threads` in the `config.yml` file as well.
- To start: `python3 lichess-bot.py`.

### LeelaChessZero: Windows CPU 2021
- For Windows modern CPUs, download the lczero binary from the [latest Lc0 release](https://github.com/LeelaChessZero/lc0/releases) (e.g. `lc0-v0.27.0-windows-cpu-dnnl.zip`).
- Unzip the file, it comes with `lc0.exe` , `dnnl.dll`, and a weights file example, `703810.pb.gz` (amongst other files).
- All three main files need to be copied to the `engines` directory.
- The `lc0.exe` should be doubleclicked and the windows safesearch warning about it being unsigned should be cleared (be careful and be sure you have the genuine file).
- Change the `engine.name` key in the `config.yml` file to `lc0.exe`, no need to edit the `config.yml` file concerning the weights file as the `lc0.exe` will use whatever `*.pb.gz` is in the same folder (have only one `*pb.gz` file in the `engines` directory).
- To start: `python3 lichess-bot.py`.

**Next step**: [Configure lichess-bot](https://github.com/lichess-bot-devs/lichess-bot/wiki/Configure-lichess-bot)

**Previous step**: [Create a lichess OAuth token](https://github.com/lichess-bot-devs/lichess-bot/wiki/How-to-create-a-Lichess-OAuth-token)
