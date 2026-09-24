"""Runtime state and connection handling for one MTX.

Pure Python, no Home Assistant imports. Holds the parameter values, keeps the
session alive, reconnects and resyncs after preset recalls (spec 4.5).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import asdict
import logging
from typing import Any

from .client import (
    DeviceInfo,
    RcpClient,
    RcpCommandError,
    RcpConnectionError,
    RcpError,
    RcpTimeoutError,
    fetch_device_info,
)
from .const import (
    DEFAULT_OPTIONS,
    FIXED_UIDS,
    HEARTBEAT_INTERVAL,
    KEY_AVAILABLE,
    KEY_PRESETS,
    KEY_STATUS,
    NAME_TIMEOUT,
    READY_TIMEOUT,
    RECONNECT_MAX,
    RECONNECT_MIN,
    RESYNC_DELAY,
)
from .profiles import MtxProfile, get_profile
from .protocol import TRANSIENT_ERROR_CODES, Preset, RcpMessage, parse_preset
from .simulator import async_resolve_endpoint
from .specs import ParamSpec, build_specs

_LOGGER = logging.getLogger(__name__)

STATUS_KEYS = ("runmode", "error", "fs", "lockstatus")
PRESET_ATTRIBUTES = frozenset({"user", "preinst"})
MAX_PRESETS = 256


class MtxUnsupportedModelError(Exception):
    """The device is not a supported MTX model."""

    def __init__(self, model: str) -> None:
        """Initialize the error."""
        self.model = model or "unknown"
        super().__init__(f"Unsupported model: {self.model}")


class MtxWrongDeviceError(RcpConnectionError):
    """Another device than the configured one answers at the address."""

    def __init__(self, found: str, message: str) -> None:
        """Initialize the error."""
        super().__init__(message)
        self.found = found


class MtxDevice:
    """One Yamaha MTX processor."""

    def __init__(
        self,
        host: str,
        port: int,
        options: Mapping[str, Any],
        *,
        unique_id: str | None = None,
        name: str | None = None,
    ) -> None:
        """Initialize the device.

        unique_id and name come from the config entry. With a known unique id,
        a different device at the same address is refused.
        """
        self.host = host
        self.port = port
        self._options = {**DEFAULT_OPTIONS, **options}
        self._expected_unique_id = unique_id
        self._name_hint = name
        self.client = RcpClient(
            host,
            port,
            notify_callback=self._handle_notify,
            disconnect_callback=self._handle_disconnect,
        )
        self.info: DeviceInfo | None = None
        self.profile: MtxProfile | None = None
        self.specs: list[ParamSpec] = []
        self.values: dict[str, str] = {}
        self.unsupported: set[str] = set()
        self.status: dict[str, str] = {}
        self.presets: list[Preset] = []
        self.current_preset: int | None = None
        self.preset_modified: bool | None = None

        self._listeners: dict[str, list[Callable[[], None]]] = {}
        self._name_addresses: set[str] = set()
        self._available = False
        self._synced = False
        self._presets_loaded = False
        self._names_loaded = False
        self._stopping = False
        self._sync_lock = asyncio.Lock()
        self._disconnected = asyncio.Event()
        self._resync_handle: asyncio.TimerHandle | None = None
        self._resync_task: asyncio.Task[None] | None = None

    # Properties -----------------------------------------------------------

    @property
    def available(self) -> bool:
        """Return True when connected and synced."""
        return self._available

    @property
    def unique_id(self) -> str:
        """Return a stable id (serial number, or host as fallback)."""
        if self._expected_unique_id:
            return self._expected_unique_id
        if self.info is not None and self.info.serial:
            return self.info.serial
        return self.host

    @property
    def model(self) -> str:
        """Return the model name."""
        if self.info is not None and self.info.product:
            return self.info.product
        if self.profile is not None:
            return self.profile.model
        return "MTX"

    @property
    def name(self) -> str:
        """Return the device name as set in MTX-MRX Editor."""
        if self.info is not None and self.info.name:
            return self.info.name
        if self._name_hint:
            return self._name_hint
        return self.model

    @property
    def current_preset_entry(self) -> Preset | None:
        """Return the preset entry of the current preset."""
        for preset in self.presets:
            if preset.index == self.current_preset:
                return preset
        return None

    def entity_unique_id(self, key: str) -> str:
        """Return the unique id for an entity key."""
        return f"{self.unique_id}_{key}"

    def expected_unique_ids(self) -> set[str]:
        """Return the unique ids of all entities for the current options."""
        keys = [spec.key for spec in self.specs] + list(FIXED_UIDS)
        return {self.entity_unique_id(key) for key in keys}

    def channel_name(self, address: str | None) -> str | None:
        """Return the channel name stored at a name address."""
        if address is None:
            return None
        name = self.values.get(address)
        if name is None:
            return None
        return name.strip() or None

    def crosspoint_addresses(self, source: str, zone: int) -> tuple[str, str]:
        """Return (level, on) addresses of a matrix crosspoint.

        Raises ValueError for unknown sources or zones.
        """
        if self.profile is None:
            raise ValueError("Device not set up")
        source_channel = self.profile.matrix_source(source)
        zone_channel = self.profile.zone(zone)
        return (
            self.profile.crosspoint_level(source_channel, zone_channel),
            self.profile.crosspoint_on(source_channel, zone_channel),
        )

    # Listeners --------------------------------------------------------------

    def add_listener(
        self, key: str, callback: Callable[[], None]
    ) -> Callable[[], None]:
        """Register a callback for an address or internal key."""
        self._listeners.setdefault(key, []).append(callback)

        def _remove() -> None:
            callbacks = self._listeners.get(key)
            if callbacks and callback in callbacks:
                callbacks.remove(callback)

        return _remove

    def _notify(self, key: str) -> None:
        for callback in list(self._listeners.get(key, ())):
            callback()

    def _set_available(self, available: bool) -> None:
        if available == self._available:
            return
        self._available = available
        if available:
            _LOGGER.info("Connected to %s (%s)", self.name, self.host)
        elif not self._stopping:
            _LOGGER.info("Connection to %s (%s) lost", self.name, self.host)
        self._notify(KEY_AVAILABLE)

    # Lifecycle ----------------------------------------------------------------

    def configure_model(self, model: str) -> None:
        """Set up the parameter map without connecting (device may be offline).

        Raises MtxUnsupportedModelError for unknown models.
        """
        profile = get_profile(model)
        if profile is None:
            raise MtxUnsupportedModelError(model)
        self._apply_profile(profile)

    def _apply_profile(self, profile: MtxProfile) -> None:
        self.profile = profile
        self.specs = build_specs(profile, self._options)
        self._name_addresses = {
            spec.name_address for spec in self.specs if spec.name_address is not None
        }

    async def async_setup(self) -> DeviceInfo:
        """Connect and read device info. Parameters are synced by async_run."""
        await self._async_connect()
        info = await fetch_device_info(self.client)
        profile = get_profile(info.product)
        if profile is None:
            await self.client.close()
            raise MtxUnsupportedModelError(info.product)
        self._check_identity(info)
        self.info = info
        if self.profile is None:
            self._apply_profile(profile)
        return info

    async def async_run(self) -> None:
        """Keep the session alive; reconnect and resync when needed."""
        backoff = RECONNECT_MIN
        failure_logged = False
        while not self._stopping:
            try:
                if not self.client.connected:
                    await self._async_reconnect()
                if not self._synced:
                    await self.async_sync(full=True)
                    self._synced = True
                    self._set_available(True)
                    backoff = RECONNECT_MIN
                    failure_logged = False
                await self._async_heartbeat()
            except RcpError as err:
                if self._stopping:
                    break
                if failure_logged:
                    _LOGGER.debug("Still no connection to %s: %s", self.host, err)
                else:
                    _LOGGER.warning(
                        "Communication with %s (%s) failed: %s; retrying",
                        self.name,
                        self.host,
                        err,
                    )
                    failure_logged = True
                self._synced = False
                self._set_available(False)
                await self.client.close()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, RECONNECT_MAX)

    async def async_shutdown(self) -> None:
        """Stop and disconnect."""
        self._stopping = True
        if self._resync_handle is not None:
            self._resync_handle.cancel()
            self._resync_handle = None
        task = self._resync_task
        if task is not None and not task.done():
            task.cancel()
            await asyncio.wait({task})
        await self.client.close()
        self._set_available(False)

    async def _async_connect(self) -> None:
        host, port = await async_resolve_endpoint(self.host, self.port)
        self.client.set_endpoint(host, port)
        self._disconnected.clear()
        await self.client.connect(ready_timeout=READY_TIMEOUT)

    async def _async_reconnect(self) -> None:
        await self._async_connect()
        info = await fetch_device_info(self.client)
        self._check_identity(info)
        self.info = info

    def _check_identity(self, info: DeviceInfo) -> None:
        """Refuse a device that is not the configured one."""
        found = info.serial or self.host
        expected = self._expected_unique_id
        if not expected and self.info is not None:
            expected = self.info.serial
        if expected and found != expected:
            raise MtxWrongDeviceError(
                found,
                f"Another device answers at {self.host} "
                f"(serial {found}, expected {expected})",
            )
        profile = get_profile(info.product)
        if self.profile is not None and profile is not self.profile:
            reported = info.product or "unknown"
            raise MtxWrongDeviceError(
                found,
                f"{self.host} reports model {reported}, expected {self.profile.model}",
            )

    async def _async_heartbeat(self) -> None:
        """Wait one interval, then check the device still answers."""
        try:
            await asyncio.wait_for(self._disconnected.wait(), HEARTBEAT_INTERVAL)
        except TimeoutError:
            run_mode = await self.client.devstatus("runmode")
            self._update_status("runmode", run_mode)
            return
        raise RcpConnectionError("Connection closed")

    # Sync -----------------------------------------------------------------------

    async def async_sync(self, *, full: bool = False) -> None:
        """Read status, presets and all tracked parameters (spec 4.2)."""
        async with self._sync_lock:
            await self._async_refresh_status()
            if full or not self._presets_loaded:
                await self._async_load_presets()
            await self._async_refresh_current_preset()

            addresses = list(dict.fromkeys(spec.address for spec in self.specs))
            if full or not self._names_loaded:
                addresses.extend(sorted(self._name_addresses))
            for address in addresses:
                await self._async_fetch(address)
            self._names_loaded = True

    async def async_request_sync(self) -> None:
        """Run a full sync now (resync button)."""
        await self.async_sync(full=True)

    async def _async_fetch(self, address: str) -> None:
        if address in self.unsupported:
            return
        optional = address in self._name_addresses
        try:
            message = await self.client.get(
                address, timeout=NAME_TIMEOUT if optional else None
            )
        except RcpCommandError as err:
            if err.code in TRANSIENT_ERROR_CODES:
                _LOGGER.debug("Temporary error reading %s: %s", address, err.code)
                return
            self._mark_unsupported(address, err.code, optional)
            return
        except RcpTimeoutError:
            # Silence can mean a dead link or an address the device ignores.
            # If the device still answers a status query it is the latter.
            await self.client.devstatus("runmode")
            self._mark_unsupported(address, "no reply", optional)
            return
        self._apply(address, message.value)

    def _mark_unsupported(self, address: str, reason: str, optional: bool) -> None:
        if optional:
            # Channel names are "notification only" in the spec. If one cannot
            # be read, skip all of them instead of waiting on each.
            _LOGGER.debug(
                "%s does not return channel names (%s); using notifications only",
                self.model,
                reason,
            )
            new = self._name_addresses - self.unsupported
            self.unsupported.update(new)
            return
        self.unsupported.add(address)
        _LOGGER.warning(
            "%s does not accept %s (%s); the related entity is unavailable",
            self.model,
            address,
            reason,
        )
        self._notify(address)

    async def _async_refresh_status(self) -> None:
        changed = False
        for key in STATUS_KEYS:
            try:
                value = await self.client.devstatus(key)
            except RcpCommandError as err:
                _LOGGER.debug("devstatus %s not available: %s", key, err.code)
                continue
            if self.status.get(key) != value:
                self.status[key] = value
                changed = True
        if changed:
            self._notify(KEY_STATUS)

    async def _async_load_presets(self) -> None:
        try:
            reply = await self.client.request("ssnum")
        except RcpCommandError as err:
            _LOGGER.debug("Preset list not available: %s", err.code)
            self.presets = []
            self._presets_loaded = True
            self._notify(KEY_PRESETS)
            return
        try:
            count = min(int(reply.args[0]), MAX_PRESETS)
        except (IndexError, ValueError):
            _LOGGER.warning("Unexpected reply to ssnum: %s", reply.raw)
            return

        presets: list[Preset] = []
        for index in range(count):
            try:
                info = await self.client.request(f"ssinfo {index}")
            except RcpCommandError as err:
                _LOGGER.debug("ssinfo %s failed: %s", index, err.code)
                continue
            preset = parse_preset(info)
            if preset is not None and preset.attribute in PRESET_ATTRIBUTES:
                presets.append(preset)
        self.presets = presets
        self._presets_loaded = True
        self._notify(KEY_PRESETS)

    async def _async_refresh_current_preset(self) -> None:
        try:
            reply = await self.client.request("sscurrent")
        except RcpCommandError as err:
            _LOGGER.debug("Current preset not available: %s", err.code)
            current, modified = None, None
        else:
            current = _parse_int(reply.args[0]) if reply.args else None
            modified = reply.args[1] == "modified" if len(reply.args) > 1 else None
        if (current, modified) != (self.current_preset, self.preset_modified):
            self.current_preset = current
            self.preset_modified = modified
            self._notify(KEY_PRESETS)

    def schedule_resync(self, delay: float = RESYNC_DELAY) -> None:
        """Schedule a (debounced) resync of all parameters."""
        if self._stopping:
            return
        if self._resync_handle is not None:
            self._resync_handle.cancel()
        self._resync_handle = asyncio.get_running_loop().call_later(
            delay, self._start_resync
        )

    def _start_resync(self) -> None:
        self._resync_handle = None
        if not self._synced or self._stopping:
            return
        if self._resync_task is not None and not self._resync_task.done():
            self.schedule_resync()
            return
        self._resync_task = asyncio.get_running_loop().create_task(
            self._async_resync(), name=f"yamaha_mtx_resync_{self.host}"
        )

    async def _async_resync(self) -> None:
        try:
            await self.async_sync()
        except RcpError as err:
            _LOGGER.warning("Resync of %s failed: %s", self.name, err)

    # Control ------------------------------------------------------------------

    async def async_set_param(self, address: str, value: int | str) -> None:
        """Set a parameter and apply the value the device confirms."""
        reply = await self.client.set(address, value)
        self._apply(address, reply.value)

    async def async_recall_preset(self, index: int) -> None:
        """Recall a preset and resync afterwards."""
        await self.client.request(f"ssrecall {index}")
        self.current_preset = index
        self.preset_modified = False
        self._notify(KEY_PRESETS)
        self.schedule_resync()

    async def async_send_raw(self, command: str) -> str:
        """Send a raw command and return the reply line (also for ERROR)."""
        try:
            reply = await self.client.request(command, strict=False)
        except RcpCommandError as err:
            return err.raw
        if reply.command == "set" and reply.address is not None:
            self._apply(reply.address, reply.value)
        return reply.raw

    # Incoming -------------------------------------------------------------------

    def _apply(self, address: str, value: str | None) -> None:
        if value is None or self.values.get(address) == value:
            return
        self.values[address] = value
        self._notify(address)

    def _update_status(self, key: str, value: str) -> None:
        previous = self.status.get(key)
        if previous == value:
            return
        self.status[key] = value
        self._notify(KEY_STATUS)
        if key == "runmode" and value == "normal" and previous is not None:
            self.schedule_resync()

    def _handle_notify(self, message: RcpMessage) -> None:
        command = message.command
        args = message.args
        if command == "set":
            if message.address is not None:
                self._apply(message.address, message.value)
        elif command == "sscurrent":
            current = _parse_int(args[0]) if args else None
            if current != self.current_preset:
                self.current_preset = current
                self.preset_modified = False
                self._notify(KEY_PRESETS)
            self.schedule_resync()
        elif command in ("ssrecall", "sscurrent_ex", "ssrecall_ex"):
            self.schedule_resync()
        elif command == "devstatus":
            if len(args) >= 2:
                self._update_status(args[0], args[1])
        elif command == "event":
            if (
                len(args) >= 2
                and args[0] == "MTX:SynchronizationSetStatus"
                and args[1] == "inactive"
            ):
                # MTX-MRX Editor pushed a new configuration.
                self._presets_loaded = False
                self._names_loaded = False
                self.unsupported.clear()
                self.schedule_resync()
        elif command in ("setn", "mtr"):
            return
        else:
            _LOGGER.debug("Unhandled notification: %s", message.raw)

    def _handle_disconnect(self) -> None:
        self._synced = False
        self._disconnected.set()
        if self._resync_handle is not None:
            self._resync_handle.cancel()
            self._resync_handle = None
        self._set_available(False)

    # Diagnostics ----------------------------------------------------------------

    def as_diagnostics(self) -> dict[str, Any]:
        """Return a snapshot for diagnostics."""
        return {
            "info": asdict(self.info) if self.info is not None else None,
            "model_profile": self.profile.model if self.profile is not None else None,
            "available": self._available,
            "options": self._options,
            "status": dict(self.status),
            "presets": [asdict(preset) for preset in self.presets],
            "current_preset": self.current_preset,
            "preset_modified": self.preset_modified,
            "entity_count": len(self.specs) + len(FIXED_UIDS),
            "unsupported_addresses": sorted(self.unsupported),
            "values": dict(sorted(self.values.items())),
        }


def _parse_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None
