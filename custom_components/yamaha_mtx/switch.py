"""Switch entities (channel on, DCA mute, crosspoints, scheduler) for Yamaha MTX."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import MtxConfigEntry, MtxParamEntity
from .specs import PLATFORM_SWITCH

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MtxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up switch entities."""
    device = entry.runtime_data
    async_add_entities(
        MtxParamSwitch(device, spec)
        for spec in device.specs
        if spec.platform == PLATFORM_SWITCH
    )


class MtxParamSwitch(MtxParamEntity, SwitchEntity):
    """An on/off parameter. The state follows the device value (1 = on)."""

    @property
    def is_on(self) -> bool | None:
        """Return True when the parameter is on."""
        raw = self.raw_int
        if raw is None:
            return None
        return raw == 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the parameter on."""
        await self.async_set_raw(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the parameter off."""
        await self.async_set_raw(0)
