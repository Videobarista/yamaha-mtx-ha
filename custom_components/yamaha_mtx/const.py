"""Constants for the Yamaha MTX integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "yamaha_mtx"
MANUFACTURER: Final = "Yamaha"

# Yamaha Remote Control Protocol (RCP) runs on this TCP port.
DEFAULT_PORT: Final = 49280

# Config entry data: the model, so entities exist while the device is offline.
CONF_MODEL: Final = "model"

# Models with a built-in parameter map.
SUPPORTED_MODELS: Final = ("MTX3", "MTX5-D")

# Entering one of these as host starts a built-in simulated device.
SIMULATOR_HOSTS: Final[dict[str, str]] = {
    "simulator": "MTX3",
    "simulator-mtx3": "MTX3",
    "simulator-mtx5d": "MTX5-D",
    "simulator-mtx5-d": "MTX5-D",
}

# Options: which entity groups to create.
OPT_INPUTS: Final = "inputs"
OPT_ZONES: Final = "zones"
OPT_OUTPUTS: Final = "outputs"
OPT_ROUTER: Final = "router"
OPT_DCA: Final = "dca"
OPT_MATRIX: Final = "matrix"

DEFAULT_OPTIONS: Final[dict[str, bool]] = {
    OPT_INPUTS: True,
    OPT_ZONES: True,
    OPT_OUTPUTS: True,
    OPT_ROUTER: True,
    OPT_DCA: False,
    OPT_MATRIX: False,
}

# Level handling (dB).
LEVEL_MIN_DB: Final = -80.0
LEVEL_STEP_DB: Final = 0.5
# -infinity is shown as this value, it is the bottom of the Yamaha fader table.
NEG_INF_DB: Final = -138.0

# Timing (seconds unless stated otherwise).
CONNECT_TIMEOUT: Final = 10.0
REQUEST_TIMEOUT: Final = 5.0
READY_TIMEOUT: Final = 15.0
READY_POLL_TIMEOUT: Final = 1.5
NAME_TIMEOUT: Final = 2.0
HEARTBEAT_INTERVAL: Final = 10.0
DEVICE_KEEPALIVE_MS: Final = 30000
RECONNECT_MIN: Final = 5.0
RECONNECT_MAX: Final = 60.0
RESYNC_DELAY: Final = 1.5

# Internal listener keys (never valid RCP addresses).
KEY_AVAILABLE: Final = "__available__"
KEY_STATUS: Final = "__status__"
KEY_PRESETS: Final = "__presets__"

# Unique id suffixes of fixed (non-parameter) entities.
UID_CONNECTION: Final = "connection"
UID_PRESET: Final = "preset"
UID_RESYNC: Final = "resync"
UID_RUN_MODE: Final = "run_mode"
UID_ALERT: Final = "alert"
UID_SAMPLING_RATE: Final = "sampling_rate"
UID_WORD_CLOCK: Final = "word_clock"
FIXED_UIDS: Final = (
    UID_CONNECTION,
    UID_PRESET,
    UID_RESYNC,
    UID_RUN_MODE,
    UID_ALERT,
    UID_SAMPLING_RATE,
    UID_WORD_CLOCK,
)

ATTR_CHANNEL_NAME: Final = "channel_name"

# Actions (services).
SERVICE_SET_CROSSPOINT: Final = "set_crosspoint"
SERVICE_SEND_COMMAND: Final = "send_command"
ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_SOURCE: Final = "source"
ATTR_ZONE: Final = "zone"
ATTR_LEVEL: Final = "level"
ATTR_ENABLED: Final = "enabled"
ATTR_COMMAND: Final = "command"
