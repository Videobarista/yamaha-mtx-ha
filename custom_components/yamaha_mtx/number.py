"""Number entities (fader levels in dB) for Yamaha MTX."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import LEVEL_MIN_DB, LEVEL_STEP_DB, NEG_INF_DB
from .device import MtxDevice
from .entity import MtxConfigEntry, MtxParamEntity
from .protocol import db_to_raw, raw_to_db
from .specs import PLATFORM_NUMBER, ParamSpec

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MtxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up level entities."""
    device = entry.runtime_data
    async_add_entities(
        MtxLevelNumber(device, spec)
        for spec in device.specs
        if spec.platform == PLATFORM_NUMBER
    )


class MtxLevelNumber(MtxParamEntity, NumberEntity):
    """A fader level in dB (-infinity is shown as -138 dB)."""

    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = LEVEL_MIN_DB
    _attr_native_step = LEVEL_STEP_DB
    _attr_native_unit_of_measurement = "dB"

    def __init__(self, device: MtxDevice, spec: ParamSpec) -> None:
        """Initialize the entity."""
        super().__init__(device, spec)
        self._attr_native_max_value = spec.max_db

    @property
    def native_value(self) -> float | None:
        """Return the level in dB."""
        raw = self.raw_int
        if raw is None:
            return None
        level = raw_to_db(raw)
        return NEG_INF_DB if level is None else level

    async def async_set_native_value(self, value: float) -> None:
        """Set the level."""
        await self.async_set_raw(db_to_raw(value))
