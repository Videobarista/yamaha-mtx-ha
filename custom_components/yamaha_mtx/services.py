"""Actions for the Yamaha MTX integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .client import RcpError
from .const import (
    ATTR_COMMAND,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_ENABLED,
    ATTR_LEVEL,
    ATTR_SOURCE,
    ATTR_ZONE,
    DOMAIN,
    LEVEL_MIN_DB,
    SERVICE_SEND_COMMAND,
    SERVICE_SET_CROSSPOINT,
)
from .device import MtxDevice
from .protocol import db_to_raw

SET_CROSSPOINT_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
            vol.Required(ATTR_SOURCE): cv.string,
            vol.Required(ATTR_ZONE): vol.All(vol.Coerce(int), vol.Range(min=1, max=16)),
            vol.Optional(ATTR_LEVEL): vol.All(
                vol.Coerce(float), vol.Range(min=LEVEL_MIN_DB, max=0.0)
            ),
            vol.Optional(ATTR_ENABLED): cv.boolean,
        }
    ),
    cv.has_at_least_one_key(ATTR_LEVEL, ATTR_ENABLED),
)

SEND_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_COMMAND): cv.string,
    }
)


def _get_device(hass: HomeAssistant, call: ServiceCall) -> MtxDevice:
    """Return the connected device of the config entry in the call."""
    entry_id: str = call.data[ATTR_CONFIG_ENTRY_ID]
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_found",
            translation_placeholders={"entry_id": entry_id},
        )
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_loaded",
            translation_placeholders={"title": entry.title},
        )
    device: MtxDevice = entry.runtime_data
    if not device.available:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="not_connected",
            translation_placeholders={"device": device.name},
        )
    return device


async def _async_set_crosspoint(hass: HomeAssistant, call: ServiceCall) -> None:
    """Set level and/or on state of one matrix crosspoint."""
    device = _get_device(hass, call)
    source: str = call.data[ATTR_SOURCE]
    zone: int = call.data[ATTR_ZONE]
    try:
        level_address, on_address = device.crosspoint_addresses(source, zone)
    except ValueError as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_crosspoint",
            translation_placeholders={
                "device": device.name,
                "source": source,
                "zone": str(zone),
            },
        ) from err

    level: float | None = call.data.get(ATTR_LEVEL)
    enabled: bool | None = call.data.get(ATTR_ENABLED)
    try:
        if level is not None:
            await device.async_set_param(level_address, db_to_raw(level))
        if enabled is not None:
            await device.async_set_param(on_address, 1 if enabled else 0)
    except RcpError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="set_failed",
            translation_placeholders={"device": device.name, "error": str(err)},
        ) from err


async def _async_send_command(
    hass: HomeAssistant, call: ServiceCall
) -> ServiceResponse:
    """Send a raw RCP command and return the reply line."""
    device = _get_device(hass, call)
    command: str = call.data[ATTR_COMMAND].strip()
    if not command or "\n" in command or "\r" in command:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_command",
        )
    try:
        reply = await device.async_send_raw(command)
    except RcpError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="command_failed",
            translation_placeholders={"device": device.name, "error": str(err)},
        ) from err
    return {"command": command, "reply": reply}


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration actions."""

    async def _handle_set_crosspoint(call: ServiceCall) -> None:
        await _async_set_crosspoint(hass, call)

    async def _handle_send_command(call: ServiceCall) -> ServiceResponse:
        return await _async_send_command(hass, call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_CROSSPOINT,
        _handle_set_crosspoint,
        schema=SET_CROSSPOINT_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_COMMAND,
        _handle_send_command,
        schema=SEND_COMMAND_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
