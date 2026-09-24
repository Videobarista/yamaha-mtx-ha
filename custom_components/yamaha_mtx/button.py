"""Button entities for Yamaha MTX."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .client import RcpError
from .const import DOMAIN, UID_RESYNC
from .device import MtxDevice
from .entity import MtxConfigEntry, MtxEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MtxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up button entities."""
    async_add_entities([MtxResyncButton(entry.runtime_data)])


class MtxResyncButton(MtxEntity, ButtonEntity):
    """Read all parameters from the device again."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, device: MtxDevice) -> None:
        """Initialize the entity."""
        super().__init__(device, UID_RESYNC, "resync")

    async def async_press(self) -> None:
        """Run a full sync."""
        try:
            await self._device.async_request_sync()
        except RcpError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="resync_failed",
                translation_placeholders={
                    "device": self._device.name,
                    "error": str(err),
                },
            ) from err
