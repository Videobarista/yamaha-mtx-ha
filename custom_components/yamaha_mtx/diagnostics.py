"""Diagnostics for the Yamaha MTX integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .entity import MtxConfigEntry

TO_REDACT = {CONF_HOST, "serial", "unique_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MtxConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "device": async_redact_data(entry.runtime_data.as_diagnostics(), TO_REDACT),
    }
