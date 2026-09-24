"""Connection sensor for Yamaha MTX."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import UID_CONNECTION
from .device import MtxDevice
from .entity import MtxConfigEntry, MtxEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MtxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the connection sensor."""
    async_add_entities([MtxConnectionSensor(entry.runtime_data)])


class MtxConnectionSensor(MtxEntity, BinarySensorEntity):
    """Shows whether the MTX is connected. Stays available while offline."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, device: MtxDevice) -> None:
        """Initialize the entity."""
        super().__init__(device, UID_CONNECTION, "connection")

    @property
    def available(self) -> bool:
        """Return True, the connection state is always known."""
        return True

    @property
    def is_on(self) -> bool:
        """Return True when connected and synced."""
        return self._device.available
