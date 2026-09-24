"""Asyncio client for the Yamaha Remote Control Protocol (RCP).

Pure Python, no Home Assistant imports. One request is in flight at a time;
replies are matched on command name and first option (the parameter address
for get/set). NOTIFY lines are handed to a callback as they arrive.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import logging

from .const import (
    CONNECT_TIMEOUT,
    DEFAULT_PORT,
    DEVICE_KEEPALIVE_MS,
    READY_POLL_TIMEOUT,
    READY_TIMEOUT,
    REQUEST_TIMEOUT,
)
from .protocol import KIND_NOTIFY, REPLY_KINDS, RcpMessage, parse_line, quote, tokenize

_LOGGER = logging.getLogger(__name__)

# Run modes in which the device accepts a remote control session.
READY_RUN_MODES = frozenset({"normal", "emergency"})


class RcpError(Exception):
    """Base error for RCP communication."""


class RcpConnectionError(RcpError):
    """Connection could not be made or was lost."""


class RcpTimeoutError(RcpError):
    """The device did not reply in time."""


class RcpNotReadyError(RcpConnectionError):
    """The device did not report a usable run mode in time."""


class RcpCommandError(RcpError):
    """The device answered with ERROR."""

    def __init__(self, command: str, code: str, raw: str) -> None:
        """Initialize the error."""
        super().__init__(f"{command}: {code}")
        self.command = command
        self.code = code
        self.raw = raw


@dataclass(slots=True)
class _Pending:
    """A request waiting for its reply."""

    command: str
    first_option: str | None
    future: asyncio.Future[RcpMessage]


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """Static information reported by the device."""

    product: str
    serial: str
    name: str
    firmware: str
    protocol_version: str
    parameter_set_version: str
    device_id: str


class RcpClient:
    """Single TCP session with a Yamaha RCP device."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        *,
        notify_callback: Callable[[RcpMessage], None] | None = None,
        disconnect_callback: Callable[[], None] | None = None,
        request_timeout: float = REQUEST_TIMEOUT,
    ) -> None:
        """Initialize the client."""
        self._host = host
        self._port = port
        self._notify_callback = notify_callback
        self._disconnect_callback = disconnect_callback
        self._request_timeout = request_timeout
        self._writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._pending: _Pending | None = None

    @property
    def host(self) -> str:
        """Return the host currently used."""
        return self._host

    @property
    def port(self) -> int:
        """Return the port currently used."""
        return self._port

    def set_endpoint(self, host: str, port: int) -> None:
        """Change host and port (used for the built-in simulator)."""
        self._host = host
        self._port = port

    @property
    def connected(self) -> bool:
        """Return True while the TCP session is open."""
        return (
            self._writer is not None
            and self._reader_task is not None
            and not self._reader_task.done()
        )

    async def connect(self, ready_timeout: float = READY_TIMEOUT) -> None:
        """Open the session and wait until the device is ready."""
        if self.connected:
            return
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=CONNECT_TIMEOUT,
            )
        except (OSError, TimeoutError) as err:
            reason = str(err) or type(err).__name__
            raise RcpConnectionError(
                f"Cannot connect to {self._host}:{self._port}: {reason}"
            ) from err

        self._writer = writer
        self._reader_task = asyncio.get_running_loop().create_task(
            self._read_loop(reader), name=f"yamaha_rcp_reader_{self._host}"
        )
        try:
            await self._wait_until_ready(ready_timeout)
            await self._configure_session()
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        """Close the session."""
        writer = self._writer
        task = self._reader_task
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError as err:
                _LOGGER.debug(
                    "Error while closing connection to %s: %s", self._host, err
                )
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
            await asyncio.wait({task})

    async def request(
        self, command: str, *, timeout: float | None = None, strict: bool = True
    ) -> RcpMessage:
        """Send a command and return the OK/OKm reply.

        Raises RcpCommandError when the device answers with ERROR.
        With strict=False only the command name has to match (raw commands).
        """
        if "\n" in command or "\r" in command:
            raise ValueError("Command must be a single line")
        tokens = tokenize(command)
        if not tokens:
            raise ValueError("Empty command")

        async with self._lock:
            writer = self._writer
            if writer is None or not self.connected:
                raise RcpConnectionError("Not connected")
            loop = asyncio.get_running_loop()
            future: asyncio.Future[RcpMessage] = loop.create_future()
            first_option = tokens[1] if strict and len(tokens) > 1 else None
            self._pending = _Pending(tokens[0], first_option, future)
            try:
                _LOGGER.debug("%s <- %s", self._host, command)
                writer.write(f"{command}\n".encode())
                await writer.drain()
                return await asyncio.wait_for(
                    future,
                    timeout if timeout is not None else self._request_timeout,
                )
            except TimeoutError as err:
                raise RcpTimeoutError(f"No reply to '{command}'") from err
            except OSError as err:
                raise RcpConnectionError(f"Sending '{command}' failed: {err}") from err
            finally:
                self._pending = None

    async def get(self, address: str, *, timeout: float | None = None) -> RcpMessage:
        """Query a parameter (raw value)."""
        return await self.request(f"get {address} 0 0", timeout=timeout)

    async def set(self, address: str, value: int | str) -> RcpMessage:
        """Set a parameter (raw value)."""
        option = str(value) if isinstance(value, int) else quote(value)
        return await self.request(f"set {address} 0 0 {option}")

    async def devstatus(self, key: str, *, timeout: float | None = None) -> str:
        """Query a devstatus value (runmode, error, fs, lockstatus)."""
        message = await self.request(f"devstatus {key}", timeout=timeout)
        return message.args[1] if len(message.args) > 1 else ""

    async def devinfo(self, key: str) -> str:
        """Query a devinfo value (productname, serialno, ...)."""
        message = await self.request(f"devinfo {key}")
        return message.args[1] if len(message.args) > 1 else ""

    async def _wait_until_ready(self, ready_timeout: float) -> None:
        """Poll 'devstatus runmode' until the device is ready (spec 4.1)."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + ready_timeout
        last_state = "no reply"
        while True:
            try:
                run_mode = await self.devstatus("runmode", timeout=READY_POLL_TIMEOUT)
            except RcpTimeoutError:
                last_state = "no reply"
            except RcpCommandError as err:
                last_state = err.code
            else:
                if run_mode in READY_RUN_MODES:
                    return
                last_state = f"run mode {run_mode}"
            if not self.connected:
                raise RcpConnectionError("Connection closed during handshake")
            if loop.time() >= deadline:
                raise RcpNotReadyError(f"Device not ready ({last_state})")
            await asyncio.sleep(1.0)

    async def _configure_session(self) -> None:
        """Set encoding, value mode and device side keepalive."""
        for command in (
            "scpmode encoding utf8",
            "scpmode valuetype raw",
            f"scpmode keepalive {DEVICE_KEEPALIVE_MS}",
        ):
            try:
                await self.request(command)
            except RcpCommandError as err:
                _LOGGER.warning("%s rejected '%s': %s", self._host, command, err.code)

    async def _read_loop(self, reader: asyncio.StreamReader) -> None:
        """Read lines until the connection closes."""
        try:
            while True:
                line = await reader.readline()
                if not line:
                    _LOGGER.debug("Connection closed by %s", self._host)
                    break
                text = line.decode("utf-8", errors="replace").rstrip("\r\n")
                if text.strip():
                    self._handle_line(text)
        except (OSError, ValueError) as err:
            _LOGGER.debug("Read error from %s: %s", self._host, err)
        finally:
            self._connection_lost()

    def _handle_line(self, text: str) -> None:
        """Dispatch one received line."""
        _LOGGER.debug("%s -> %s", self._host, text)
        message = parse_line(text)
        if message is None:
            _LOGGER.debug("Ignoring unrecognised line from %s: %s", self._host, text)
            return

        if message.kind == KIND_NOTIFY:
            if self._notify_callback is not None:
                try:
                    self._notify_callback(message)
                except Exception:
                    _LOGGER.exception("Error handling notification: %s", text)
            return

        if message.kind not in REPLY_KINDS:
            return
        pending = self._pending
        if pending is None or pending.future.done():
            _LOGGER.debug("Unsolicited reply from %s: %s", self._host, text)
            return
        if message.command != pending.command:
            _LOGGER.debug("Reply for another command from %s: %s", self._host, text)
            return
        if message.is_error:
            pending.future.set_exception(
                RcpCommandError(message.command, message.error_code, text)
            )
            return
        if pending.first_option is not None and (
            not message.args or message.args[0] != pending.first_option
        ):
            _LOGGER.debug("Stale reply from %s: %s", self._host, text)
            return
        pending.future.set_result(message)

    def _connection_lost(self) -> None:
        """Clean up after the reader stopped."""
        writer = self._writer
        self._writer = None
        if writer is not None:
            writer.close()
        pending = self._pending
        if pending is not None and not pending.future.done():
            pending.future.set_exception(RcpConnectionError("Connection lost"))
        if self._disconnect_callback is not None:
            try:
                self._disconnect_callback()
            except Exception:
                _LOGGER.exception("Error in disconnect handler")


async def fetch_device_info(client: RcpClient) -> DeviceInfo:
    """Read the product information of a connected device."""

    async def _optional(key: str) -> str:
        try:
            return (await client.devinfo(key)).strip()
        except RcpCommandError as err:
            _LOGGER.debug("devinfo %s not available: %s", key, err.code)
            return ""

    product = (await client.devinfo("productname")).strip()
    return DeviceInfo(
        product=product,
        serial=await _optional("serialno"),
        name=await _optional("devicename"),
        firmware=await _optional("version"),
        protocol_version=await _optional("protocolver"),
        parameter_set_version=await _optional("paramsetver"),
        device_id=await _optional("deviceid"),
    )
