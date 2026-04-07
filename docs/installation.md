# Installation

## Environment Variable Reference

These variables control where ORB stores its files. All are optional — ORB derives
sensible defaults from the install location automatically.

| Variable | Default | Description |
|---|---|---|
| `ORB_ROOT_DIR` | Derived from install type (see below) | Root directory for all ORB data. Setting this overrides all other directory defaults. |
| `ORB_CONFIG_DIR` | `$ORB_ROOT_DIR/config` | Configuration files (`config.json`, templates). |
| `ORB_WORK_DIR` | `$ORB_ROOT_DIR/work` | Working data (request state, provider output). |
| `ORB_LOG_DIR` | `$ORB_ROOT_DIR/logs` | ORB process log files. |
| `ORB_SCRIPTS_DIR` | `$ORB_ROOT_DIR/scripts` | Provider scripts (e.g. `invoke_provider.sh` for HostFactory). |
| `ORB_VENV_PATH` | _(unset)_ | Path to a Python virtualenv. When set, `invoke_provider.sh` activates it before running `orb`. |
| `ORB_HEALTH_DIR` | `$ORB_WORK_DIR/health` | Health-check output files written by `orb system health`. |
| `ORB_CACHE_DIR` | `$ORB_WORK_DIR/.cache` | Internal cache (template resolution, provider metadata). |

### Default root location by install type

| Install type | Default `ORB_ROOT_DIR` |
|---|---|
| virtualenv (standard) | Parent of the venv directory |
| virtualenv (uv tool / mise) | `~/.orb` |
| `pip install --user` | `~/.orb` |
| System install (`/usr`, `/opt`) | `$sys.prefix/orb` (falls back to `~/.orb` if not writable) |
| Development (pyproject.toml found) | Repository root |

---

## Install Scenarios

### System install (root)

```bash
sudo pip install orb-py
sudo orb init --non-interactive \
  --provider aws --region us-east-1 \
  --subnet-ids subnet-aaa111 \
  --security-group-ids sg-11111111
```

ORB writes config to `/usr/orb/config/` (or `/opt/orb/config/` depending on your
Python prefix). Override with `ORB_ROOT_DIR` if needed:

```bash
sudo ORB_ROOT_DIR=/etc/orb orb init --non-interactive ...
```

### System install (non-root)

When the system prefix is not writable, ORB automatically falls back to `~/.orb`:

```bash
pip install orb-py          # system Python, no sudo
orb init                    # writes to ~/.orb/config/
```

Or pin the location explicitly:

```bash
export ORB_ROOT_DIR=~/.orb
orb init --non-interactive --provider aws --region us-east-1 \
  --subnet-ids subnet-aaa111 --security-group-ids sg-11111111
```

### Virtualenv install

```bash
python -m venv .venv
source .venv/bin/activate
pip install "orb-py[all]"
orb init
```

ORB detects the venv and uses its parent directory as the root, so config lands
next to your project:

```
my-project/
  .venv/
  orb/config/config.json   ← written here
  orb/logs/
  orb/work/
```

### Install with --prefix

```bash
pip install --prefix /opt/myapp orb-py
export ORB_ROOT_DIR=/opt/myapp/orb
export PATH="/opt/myapp/bin:$PATH"
orb init --non-interactive --provider aws --region us-east-1 \
  --subnet-ids subnet-aaa111 --security-group-ids sg-11111111
```

---

## HostFactory Integration Guide

ORB ships an `invoke_provider.sh` script that HostFactory calls for each
provisioning operation. After `orb init`, the script is copied to `ORB_SCRIPTS_DIR`.

### Environment variables to set in HostFactory

Configure these in your HostFactory provider definition or the environment where
the HF daemon runs:

| Variable | Required | Description |
|---|---|---|
| `ORB_CONFIG_DIR` | Yes | Points HF to the ORB config directory. |
| `ORB_WORK_DIR` | Recommended | Separates ORB working data from HF working data. |
| `ORB_LOG_DIR` | Recommended | ORB process logs (distinct from `HF_LOGDIR`). |
| `ORB_VENV_PATH` | If using venv | Path to the venv containing `orb`. The script activates it automatically. |
| `HF_LOGDIR` | Set by HF | HostFactory log directory — `invoke_provider.sh` appends to `$HF_LOGDIR/scripts.log`. Do not set this yourself. |
| `HF_LOGGING_CONSOLE_ENABLED` | No | Set to `false` (default) to suppress ORB console output in HF script context. |
| `USE_LOCAL_DEV` | Dev only | Set to `true` to run ORB from source instead of the installed package. |

### Where scripts go

After `orb init`, provider scripts are placed in `ORB_SCRIPTS_DIR` (default:
`$ORB_ROOT_DIR/scripts`). Point HostFactory's `providerCommandPath` at this
directory:

```json
{
  "providerCommandPath": "/opt/myapp/orb/scripts"
}
```

The key script is `invoke_provider.sh`. It:

1. Sources `$ORB_VENV_PATH/bin/activate` if `ORB_VENV_PATH` is set.
2. Locates the `orb` command (installed package or local dev mode).
3. Passes all HF arguments through verbatim to `orb`.
4. Appends stdout/stderr to `$HF_LOGDIR/scripts.log`.

### Minimal HF provider config example

```bash
export ORB_CONFIG_DIR=/opt/myapp/orb/config
export ORB_WORK_DIR=/opt/myapp/orb/work
export ORB_LOG_DIR=/opt/myapp/orb/logs
export ORB_VENV_PATH=/opt/myapp/.venv
```

Then in your HostFactory `hostProviders` config:

```json
{
  "name": "orb-provider",
  "providerCommandPath": "/opt/myapp/orb/scripts",
  "providerCommand": "invoke_provider.sh"
}
```
