"""Built-in simulated MTX3 / MTX5-D.

Entering "simulator" (MTX3) or "simulator-mtx5d" (MTX5-D) as host starts a
small RCP server on 127.0.0.1 inside Home Assistant. It speaks the same
protocol over TCP as a real unit, so dashboards and automations can be built
before the hardware is on site. Values are kept in memory only.

Pure Python, no Home Assistant imports.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging

from .const import DEFAULT_OPTIONS, SIMULATOR_HOSTS
from .profiles import PROFILES, SCHEDULER_ADDRESS, MtxProfile
from .protocol import NEG_INF_RAW, format_level, quote, tokenize
from .specs import PLATFORM_NUMBER, PLATFORM_SELECT, PLATFORM_SWITCH, build_specs

_LOGGER = logging.getLogger(__name__)

KIND_LEVEL = "level"
KIND_SWITCH = "switch"
KIND_ENUM = "enum"
KIND_NAME = "name"

PRESET_COUNT = 51
SIM_PRESETS = {1: "Default", 2: "Evening", 3: "Night"}


@dataclass(slots=True)
class _Param:
    kind: str
    value: int | str
    maximum: int = 0
    options: tuple[str, ...] = ()

    def display(self) -> str:
        if self.kind == KIND_LEVEL and isinstance(self.value, int):
            return format_level(self.value)
        if self.kind == KIND_SWITCH:
            return "ON" if self.value == 1 else "OFF"
        if self.kind == KIND_ENUM and isinstance(self.value, int):
            if 0 <= self.value < len(self.options):
                return self.options[self.value]
        return str(self.value)

    def wire_value(self) -> str:
        if isinstance(self.value, str):
            return quote(self.value)
        return str(self.value)


class MtxSimulator:
    """In-memory MTX that speaks RCP on a local TCP port."""

    def __init__(self, model: str) -> None:
        """Initialize the simulator."""
        self.profile: MtxProfile = PROFILES[model]
        self.params: dict[str, _Param] = {}
        self.current_preset = 1
        self.modified = False
        self._clients: set[asyncio.StreamWriter] = set()
        self._server: asyncio.Server | None = None
        self._seed()

    def _seed(self) -> None:
        all_groups = dict.fromkeys(DEFAULT_OPTIONS, True)
        zones = len(self.profile.zones)
        for spec in build_specs(self.profile, all_groups):
            if spec.platform == PLATFORM_NUMBER:
                value = 0
                if spec.translation_key == "zone_level":
                    value = -1000
                elif spec.translation_key == "crosspoint_level":
                    value = NEG_INF_RAW
                self.params[spec.address] = _Param(
                    KIND_LEVEL, value, maximum=round(spec.max_db * 100)
                )
            elif spec.platform == PLATFORM_SWITCH:
                on = spec.translation_key in ("input_on", "zone_on", "output_on")
                self.params[spec.address] = _Param(KIND_SWITCH, 1 if on else 0)
            elif spec.platform == PLATFORM_SELECT:
                self.params[spec.address] = _Param(KIND_ENUM, 0, options=spec.options)
            if spec.name_address and spec.name_address not in self.params:
                self.params[spec.name_address] = _Param(KIND_NAME, "")

        # Mono inputs 1..n feed zone n at -6 dB; outputs follow their zone.
        for number, source in enumerate(self.profile.inputs[:zones], start=1):
            zone = self.profile.zone(number)
            self.params[self.profile.crosspoint_level(source, zone)].value = -600
            self.params[self.profile.crosspoint_on(source, zone)].value = 1
        for output in self.profile.outputs:
            self.params[self.profile.router(output)].value = output.index + 1

        for channel in self.profile.matrix_sources:
            if channel.name_address:
                self.params[channel.name_address].value = channel.label
        for zone in self.profile.zones:
            if zone.name_address:
                self.params[zone.name_address].value = f"ZONE {zone.label}"
        for output in self.profile.outputs:
            if output.name_address:
                self.params[output.name_address].value = f"OUT {output.label}"
        self.params[SCHEDULER_ADDRESS] = _Param(KIND_SWITCH, 0)

    async def async_start(self) -> int:
        """Start listening and return the port."""
        self._server = await asyncio.start_server(self._handle_client, "127.0.0.1", 0)
        port: int = self._server.sockets[0].getsockname()[1]
        _LOGGER.info("Simulated %s listening on 127.0.0.1:%s", self.profile.model, port)
        return port

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._clients.add(writer)
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue  # heartbeat
                for reply in self._process(text, writer):
                    writer.write(f"{reply}\n".encode())
                await writer.drain()
        except (OSError, ValueError) as err:
            _LOGGER.debug("Simulator client error: %s", err)
        finally:
            self._clients.discard(writer)
            writer.close()

    def _broadcast(self, line: str, exclude: asyncio.StreamWriter | None) -> None:
        for client in list(self._clients):
            if client is not exclude and not client.is_closing():
                client.write(f"{line}\n".encode())

    def _process(self, text: str, writer: asyncio.StreamWriter) -> list[str]:
        tokens = tokenize(text)
        command, args = tokens[0], tokens[1:]
        info = {
            "productname": self.profile.model,
            "serialno": f"SIM-{self.profile.model}-0001",
            "devicename": f"{self.profile.model} Simulator",
            "version": "4.00",
            "protocolver": "4.0.0",
            "paramsetver": "MTX:4.0.0",
            "deviceid": "001",
        }
        status = {
            "runmode": "normal",
            "error": "none",
            "fs": "48kHz",
            "lockstatus": "lock",
        }

        if command == "devstatus" and args and args[0] in status:
            return [f"OK devstatus {args[0]} {quote(status[args[0]])}"]
        if command == "devinfo" and args and args[0] in info:
            return [f"OK devinfo {args[0]} {quote(info[args[0]])}"]
        if command == "scpmode" and len(args) >= 2:
            return [f"OK scpmode {args[0]} {args[1]}"]
        if command == "get" and len(args) >= 3:
            param = self.params.get(args[0])
            if param is None:
                return ["ERROR get UnknownAddress"]
            return [f"OK get {args[0]} 0 0 {param.wire_value()}"]
        if command == "set" and len(args) >= 4:
            return self._set(args[0], args[3], writer)
        if command == "ssnum":
            return [f"OK ssnum {PRESET_COUNT}"]
        if command == "ssinfo" and args:
            return [self._ssinfo(args[0])]
        if command == "sscurrent":
            state = "modified" if self.modified else "unmodified"
            return [f"OK sscurrent {self.current_preset} {state}"]
        if command == "ssrecall" and args:
            return self._recall(args[0], writer)
        return [f"ERROR {command} UnknownCommand"]

    def _set(self, address: str, raw: str, writer: asyncio.StreamWriter) -> list[str]:
        param = self.params.get(address)
        if param is None:
            return ["ERROR set UnknownAddress"]
        if param.kind == KIND_NAME:
            return ["ERROR set ReadOnly"]
        try:
            value = int(raw)
        except ValueError:
            return ["ERROR set InvalidArgument"]

        kind = "OK"
        if param.kind == KIND_LEVEL:
            clamped = max(NEG_INF_RAW, min(param.maximum, value))
            kind = "OK" if clamped == value else "OKm"
            value = clamped
        elif param.kind == KIND_SWITCH and value not in (0, 1):
            return ["ERROR set InvalidArgument"]
        elif param.kind == KIND_ENUM and not 0 <= value < len(param.options):
            return ["ERROR set InvalidArgument"]

        param.value = value
        self.modified = True
        suffix = f"{address} 0 0 {value} {quote(param.display())}"
        self._broadcast(f"NOTIFY set {suffix}", exclude=writer)
        return [f"{kind} set {suffix}"]

    def _ssinfo(self, raw: str) -> str:
        try:
            index = int(raw)
        except ValueError:
            return "ERROR ssinfo InvalidArgument"
        if not 0 <= index < PRESET_COUNT:
            return "ERROR ssinfo InvalidArgument"
        title = SIM_PRESETS.get(index)
        if title is None:
            return f'OK ssinfo {index} "{index}" empty "" ""'
        return f'OK ssinfo {index} "{index}" user {quote(title)} ""'

    def _recall(self, raw: str, writer: asyncio.StreamWriter) -> list[str]:
        try:
            index = int(raw)
        except ValueError:
            return ["ERROR ssrecall InvalidArgument"]
        if index not in SIM_PRESETS:
            return ["ERROR ssrecall InvalidArgument"]
        # Each preset lowers the zone levels a bit further.
        for zone in self.profile.zones:
            self.params[self.profile.zone_level(zone)].value = -1000 - (index - 1) * 600
        self.current_preset = index
        self.modified = False
        self._broadcast(f"NOTIFY sscurrent {index}", exclude=writer)
        return [f"OK ssrecall {index}"]


_SIMULATORS: dict[str, int] = {}
_SIMULATOR_LOCK = asyncio.Lock()
_SIMULATOR_INSTANCES: list[MtxSimulator] = []


def simulator_model(host: str) -> str | None:
    """Return the simulated model for a host string, or None."""
    return SIMULATOR_HOSTS.get(host.strip().lower())


async def async_resolve_endpoint(host: str, port: int) -> tuple[str, int]:
    """Return the real endpoint, starting a simulator when requested."""
    model = simulator_model(host)
    if model is None:
        return host, port
    async with _SIMULATOR_LOCK:
        if model not in _SIMULATORS:
            simulator = MtxSimulator(model)
            _SIMULATORS[model] = await simulator.async_start()
            _SIMULATOR_INSTANCES.append(simulator)
        return "127.0.0.1", _SIMULATORS[model]
