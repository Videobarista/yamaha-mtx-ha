"""Select entities (router source, preset) for Yamaha MTX."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .client import RcpError
from .const import DOMAIN, KEY_PRESETS, UID_PRESET
from .device import MtxDevice
from .entity import MtxConfigEntry, MtxEntity, MtxParamEntity
from .specs import PLATFORM_SELECT

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MtxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up select entities."""
    device = entry.runtime_data
    entities: list[SelectEntity] = [
        MtxRouterSelect(device, spec)
        for spec in device.specs
        if spec.platform == PLATFORM_SELECT
    ]
    entities.append(MtxPresetSelect(device))
    async_add_entities(entities)


class MtxRouterSelect(MtxParamEntity, SelectEntity):
    """Source of an output channel (router)."""

    @property
    def options(self) -> list[str]:
        """Return the router sources."""
        return list(self._spec.options)

    @property
    def current_option(self) -> str | None:
        """Return the current source."""
        raw = self.raw_int
        if raw is None or not 0 <= raw < len(self._spec.options):
            return None
        return self._spec.options[raw]

    async def async_select_option(self, option: str) -> None:
        """Route another source to this output."""
        if option not in self._spec.options:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_option",
                translation_placeholders={"option": option},
            )
        await self.async_set_raw(self._spec.options.index(option))


class MtxPresetSelect(MtxEntity, SelectEntity):
    """Recall presets and show the current one."""

    def __init__(self, device: MtxDevice) -> None:
        """Initialize the entity."""
        super().__init__(device, UID_PRESET, "preset", watch=(KEY_PRESETS,))

    @property
    def options(self) -> list[str]:
        """Return the stored presets."""
        return [preset.label for preset in self._device.presets]

    @property
    def current_option(self) -> str | None:
        """Return the last recalled preset."""
        preset = self._device.current_preset_entry
        return preset.label if preset is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return preset number and whether it was changed after recall."""
        return {
            "preset_number": self._device.current_preset,
            "modified": self._device.preset_modified,
        }

    async def async_select_option(self, option: str) -> None:
        """Recall a preset."""
        for preset in self._device.presets:
            if preset.label == option:
                try:
                    await self._device.async_recall_preset(preset.index)
                except RcpError as err:
                    raise HomeAssistantError(
                        translation_domain=DOMAIN,
                        translation_key="recall_failed",
                        translation_placeholders={
                            "device": self._device.name,
                            "preset": option,
                            "error": str(err),
                        },
                    ) from err
                return
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unknown_option",
            translation_placeholders={"option": option},
        )
