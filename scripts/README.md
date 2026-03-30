# scripts

This directory stores helper scripts so that temporary data-processing logic does not leak into the main engineering code.

Suggested future contents:

- serial log parsing scripts
- experiment data cleaning scripts
- CSV conversion scripts
- result plotting scripts

The directory should stay lightweight for now and can grow after the simulation log format is stabilized.

## Python Environment

The MQTT test client in this directory uses `pyenv` and the repository-level
Python version file.

Recommended setup:

```bash
pyenv install 3.11.9
pyenv local 3.11.9
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

To confirm that `pyenv` has switched the current repository to the expected
Python interpreter:

```bash
pyenv version
pyenv which python
python --version
```

Expected result:

- `pyenv version` shows `3.11.9 (set by .../.python-version)`
- `pyenv which python` points to the `pyenv` installation path
- `python --version` reports `Python 3.11.9`

After the virtual environment is activated:

- the shell prompt usually shows `(.venv)`
- `which python` points to `.venv/bin/python`

If the version does not switch as expected, initialize `pyenv` in your shell
first and then reopen the terminal:

```bash
eval "$(pyenv init -)"
```

## MQTT Test Client

The current MQTT test client is:

- `scripts/mqtt_test_client.py`
- `scripts/mqtt_client_config.example.json`

It can be used to:

- subscribe to telemetry messages
- subscribe to parameter ACK messages
- publish an immediate parameter update
- publish a staged parameter update

To use a self-managed broker, create a local config file:

```bash
cp scripts/mqtt_client_config.example.json scripts/mqtt_client_config.json
```

Then edit the local file and fill in your actual:

- broker host
- broker port
- username
- password
- topics if needed

The local file `scripts/mqtt_client_config.json` is ignored by Git so that
broker credentials do not need to be committed.

Examples:

```bash
python scripts/mqtt_test_client.py --mode immediate
python scripts/mqtt_test_client.py --mode staged
```
