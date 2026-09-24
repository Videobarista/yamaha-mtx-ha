"""Base entities for the Yamaha MTX integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .client import RcpError
from .const import ATTR_CHANNEL_NAME, DOMAIN, KEY_AVAILABLE, MANUFACTURER
from .device import MtxDevice
from .specs import ParamSpec

type MtxConfigEntry = ConfigEntry[MtxDevice]


class MtxEntity(Entity):
    """Base class for all MTX entities (push updates, no polling)."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        device: MtxDevice,
        key: str,
        translation_key: str,
        *,
        placeholders: dict[str, str] | None = None,
        watch: tuple[str, ...] = (),
    ) -> None:
        """Initialize the entity."""
        self._device = device
        self._watch = tuple(dict.fromkeys((KEY_AVAILABLE, *watch)))
        self._attr_unique_id = device.entity_unique_id(key)
        self._attr_translation_key = translation_key
        if placeholders:
            self._attr_translation_placeholders = placeholders
        info = device.info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.unique_id)},
            manufacturer=MANUFACTURER,
            model=device.model,
            name=device.name,
            serial_number=info.serial if info is not None and info.serial else None,
            sw_version=info.firmware if info is not None and info.firmware else None,
        )

    @property
    def available(self) -> bool:
        """Return True when the device is connected and synced."""
        return self._device.available

    async def async_added_to_hass(self) -> None:
        """Subscribe to device updates."""
        await super().async_added_to_hass()
        for key in self._watch:
            self.async_on_remove(
                self._device.add_listener(key, self._async_handle_update)
            )

    @callback
    def _async_handle_update(self) -> None:
        """Write the new state."""
        self.async_write_ha_state()


class MtxParamEntity(MtxEntity):
    """Entity backed by one device parameter."""

    def __init__(self, device: MtxDevice, spec: ParamSpec) -> None:
        """Initialize the entity."""
        watch = (spec.address,)
        if spec.name_address is not None:
            watch += (spec.name_address,)
        super().__init__(
            device,
            spec.key,
            spec.translation_key,
            placeholders=dict(spec.placeholders) or None,
            watch=watch,
        )
        self._spec = spec

    @property
    def available(self) -> bool:
        """Return False when the device rejected this parameter."""
        return super().available and self._spec.address not in self._device.unsupported

    @property
    def raw_value(self) -> str | None:
        """Return the raw value as last reported by the device."""
        return self._device.values.get(self._spec.address)

    @property
    def raw_int(self) -> int | None:
        """Return the raw value as integer."""
        raw = self.raw_value
        if raw is None:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the channel name set in MTX-MRX Editor, when known."""
        name = self._device.channel_name(self._spec.name_address)
        if name is None:
            return None
        return {ATTR_CHANNEL_NAME: name}

    async def async_set_raw(self, value: int) -> None:
        """Send a new raw value to the device."""
        try:
            await self._device.async_set_param(self._spec.address, value)
        except RcpError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_failed",
                translation_placeholders={
                    "device": self._device.name,
                    "error": str(err),
                },
            ) from err
