"""The Yamaha MTX integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.typing import ConfigType

from .client import RcpError
from .const import CONF_MODEL, DOMAIN, KEY_AVAILABLE
from .device import MtxDevice, MtxUnsupportedModelError, MtxWrongDeviceError
from .entity import MtxConfigEntry
from .services import async_setup_services

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: MtxConfigEntry) -> bool:
    """Set up the entities and keep the connection to the MTX in the background."""
    host: str = entry.data[CONF_HOST]
    device = MtxDevice(
        host,
        entry.data[CONF_PORT],
        entry.options,
        unique_id=entry.unique_id,
        name=entry.title,
    )

    model: str | None = entry.data.get(CONF_MODEL)
    if model is not None:
        # The model is known: no need to reach the device now. Entities start
        # unavailable and the connection is made in the background.
        try:
            device.configure_model(model)
        except MtxUnsupportedModelError as err:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="unsupported_model",
                translation_placeholders={"host": host, "model": err.model},
            ) from err
    else:
        await _async_connect_first(hass, entry, device)

    entry.runtime_data = device
    _async_remove_stale_entities(hass, entry, device)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    @callback
    def _async_update_device_registry() -> None:
        """Store firmware and serial number once the device answers."""
        info = device.info
        if not device.available or info is None:
            return
        registry = dr.async_get(hass)
        device_entry = registry.async_get_device(
            identifiers={(DOMAIN, device.unique_id)}
        )
        if device_entry is None:
            return
        registry.async_update_device(
            device_entry.id,
            sw_version=info.firmware or None,
            serial_number=info.serial or None,
        )

    entry.async_on_unload(
        device.add_listener(KEY_AVAILABLE, _async_update_device_registry)
    )

    entry.async_create_background_task(
        hass, device.async_run(), f"{DOMAIN}_connection_{entry.entry_id}"
    )

    async def _async_stop(event: Event) -> None:
        await device.async_shutdown()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)
    )

    options = dict(entry.options)

    async def _async_entry_updated(
        hass: HomeAssistant, updated_entry: MtxConfigEntry
    ) -> None:
        # Reconfigure reloads by itself; only option changes need a reload here.
        if dict(updated_entry.options) != options:
            await hass.config_entries.async_reload(updated_entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MtxConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
    return unloaded


async def _async_connect_first(
    hass: HomeAssistant, entry: MtxConfigEntry, device: MtxDevice
) -> None:
    """Connect to learn the model (entries created without a stored model)."""
    host: str = entry.data[CONF_HOST]
    try:
        await device.async_setup()
    except MtxUnsupportedModelError as err:
        await device.async_shutdown()
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="unsupported_model",
            translation_placeholders={"host": host, "model": err.model},
        ) from err
    except MtxWrongDeviceError as err:
        await device.async_shutdown()
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="wrong_device",
            translation_placeholders={"host": host, "serial": err.found},
        ) from err
    except RcpError as err:
        await device.async_shutdown()
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"host": host, "error": str(err)},
        ) from err

    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_MODEL: device.model}
    )


def _async_remove_stale_entities(
    hass: HomeAssistant, entry: MtxConfigEntry, device: MtxDevice
) -> None:
    """Remove entities of entity groups that were switched off in the options."""
    registry = er.async_get(hass)
    expected = device.expected_unique_ids()
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registry_entry.unique_id not in expected:
            registry.async_remove(registry_entry.entity_id)
