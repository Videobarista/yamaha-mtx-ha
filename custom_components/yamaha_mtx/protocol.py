"""Yamaha Remote Control Protocol (RCP) primitives.

Pure Python, no Home Assistant imports. Implements the line format from the
Yamaha "MTX3/MTX5-D/MRX7-D/XMV/EXi8/EXo8 Remote Control Protocol
Specifications" V4.0.0:

    <command> <option 1> <option 2> ... <option n> LF

Strings are wrapped in double quotes; a backslash escapes the next character.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Final

KIND_OK: Final = "OK"
KIND_OK_MODIFIED: Final = "OKm"
KIND_ERROR: Final = "ERROR"
KIND_NOTIFY: Final = "NOTIFY"
REPLY_KINDS: Final = frozenset({KIND_OK, KIND_OK_MODIFIED, KIND_ERROR})
KNOWN_KINDS: Final = REPLY_KINDS | {KIND_NOTIFY}

# Commands whose first option is a parameter address and whose value sits at
# option 4 (after the two fixed "0 0" options).
PARAM_COMMANDS: Final = frozenset({"get", "getn", "set", "setn", "setr"})

# Raw value used by MTX devices for -infinity on level parameters.
NEG_INF_RAW: Final = -13801

# Error codes that are worth retrying later instead of marking a parameter
# as unsupported.
TRANSIENT_ERROR_CODES: Final = frozenset({"Busy", "AccessDenied", "TooLongCommand"})


def tokenize(line: str) -> list[str]:
    """Split an RCP line into options, honouring quotes and escapes."""
    tokens: list[str] = []
    buffer: list[str] = []
    in_quotes = False
    escaping = False
    has_token = False

    for char in line:
        if escaping:
            buffer.append(char)
            escaping = False
            continue
        if char == "\\":
            escaping = True
            has_token = True
            continue
        if in_quotes:
            if char == '"':
                in_quotes = False
            else:
                buffer.append(char)
            continue
        if char == '"':
            in_quotes = True
            has_token = True
            continue
        if char in " \t":
            if has_token:
                tokens.append("".join(buffer))
                buffer = []
                has_token = False
            continue
        buffer.append(char)
        has_token = True

    if has_token:
        tokens.append("".join(buffer))
    return tokens


def quote(value: str) -> str:
    """Quote a string option for sending."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


@dataclass(frozen=True, slots=True)
class RcpMessage:
    """A line received from the device."""

    kind: str
    command: str
    args: tuple[str, ...]
    raw: str

    @property
    def is_error(self) -> bool:
        """Return True for ERROR replies."""
        return self.kind == KIND_ERROR

    @property
    def address(self) -> str | None:
        """Return the parameter address for get/set style messages."""
        if self.command in PARAM_COMMANDS and self.args:
            return self.args[0]
        return None

    @property
    def value(self) -> str | None:
        """Return the value option of a get/set style message."""
        if self.command in PARAM_COMMANDS and len(self.args) > 3:
            return self.args[3]
        return None

    @property
    def text(self) -> str | None:
        """Return the display string of a set style message, if present."""
        if self.command in PARAM_COMMANDS and len(self.args) > 4:
            return self.args[4]
        return None

    @property
    def error_code(self) -> str:
        """Return the error code of an ERROR reply."""
        if self.is_error and self.args:
            return self.args[-1]
        return ""


def parse_line(line: str) -> RcpMessage | None:
    """Parse a received line. Returns None for lines that are not replies."""
    tokens = tokenize(line)
    if not tokens or tokens[0] not in KNOWN_KINDS:
        return None
    command = tokens[1] if len(tokens) > 1 else ""
    return RcpMessage(tokens[0], command, tuple(tokens[2:]), line)


def param_address(
    unique_id: int,
    element: int,
    x_pos: int = 0,
    y_pos: int = 0,
    param: int = 0,
    index: int = 0,
    memory: int = 512,
) -> str:
    """Build an MTX parameter address (MTX:mem_MemNo/UniqueId/...)."""
    return f"MTX:mem_{memory}/{unique_id}/{element}/{x_pos}/{y_pos}/{param}/{index}"


def is_neg_inf(raw: int) -> bool:
    """Return True when a raw level value means -infinity."""
    return raw <= NEG_INF_RAW


def raw_to_db(raw: int) -> float | None:
    """Convert a raw level (dB x 100) to dB. Returns None for -infinity."""
    if is_neg_inf(raw):
        return None
    return raw / 100


def db_to_raw(value: float) -> int:
    """Convert dB to a raw level value (dB x 100)."""
    return round(value * 100)


def format_level(raw: int) -> str:
    """Format a raw level the way the device does ("-77.60", "-INFINITY")."""
    if is_neg_inf(raw):
        return "-INFINITY"
    return f"{raw / 100:.2f}"


@dataclass(frozen=True, slots=True)
class Preset:
    """An entry of the device preset list."""

    index: int
    number: str
    attribute: str
    title: str

    @property
    def label(self) -> str:
        """Return the label used as select option."""
        if self.title:
            return f"{self.number}: {self.title}"
        return self.number


def parse_preset(message: RcpMessage) -> Preset | None:
    """Parse an 'OK ssinfo' reply."""
    if message.command != "ssinfo" or len(message.args) < 3:
        return None
    try:
        index = int(message.args[0])
    except ValueError:
        return None
    title = message.args[3].strip() if len(message.args) > 3 else ""
    return Preset(index, message.args[1].strip() or str(index), message.args[2], title)


_ALERT_RE: Final = re.compile(
    r"^(?P<type>flt|err|wrn)/(?P<message>.*?)//\s*x(?P<code>[0-9A-Fa-f]+)"
    r"\s+(?P<state>\S+)\s+\((?P<count>\d+)\)\s+ID-(?P<unit>[0-9A-Fa-f]+)"
    r"\s*(?P<timestamp>.*)$"
)
ALERT_TYPES: Final = {"flt": "fault", "err": "error", "wrn": "warning"}


@dataclass(frozen=True, slots=True)
class Alert:
    """A parsed device alert (devstatus error)."""

    raw: str
    message: str
    type: str | None = None
    code: str | None = None
    state: str | None = None
    count: int | None = None
    unit_id: str | None = None
    timestamp: str | None = None


def parse_alert(text: str | None) -> Alert | None:
    """Parse a devstatus error string. Returns None when there is no alert."""
    if text is None:
        return None
    stripped = text.strip()
    if not stripped or stripped.lower() == "none":
        return None
    match = _ALERT_RE.match(stripped)
    if match is None:
        return Alert(raw=stripped, message=stripped[:255])
    return Alert(
        raw=stripped,
        message=match["message"].strip()[:255] or stripped[:255],
        type=ALERT_TYPES.get(match["type"]),
        code=match["code"].upper(),
        state=match["state"],
        count=int(match["count"]),
        unit_id=match["unit"],
        timestamp=match["timestamp"].strip() or None,
    )
