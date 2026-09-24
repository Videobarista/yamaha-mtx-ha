"""Status sensors for Yamaha MTX."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    KEY_STATUS,
    UID_ALERT,
    UID_RUN_MODE,
    UID_SAMPLING_RATE,
    UID_WORD_CLOCK,
)
from .device import MtxDevice
from .entity import MtxConfigEntry, MtxEntity
from .protocol import parse_alert

PARALLEL_UPDATES = 0


def _alert_state(device: MtxDevice) -> str | None:
    raw = device.status.get("error")
    if raw is None:
        return None
    alert = parse_alert(raw)
    return "none" if alert is None else alert.message


def _alert_attributes(device: MtxDevice) -> dict[str, Any] | None:
    alert = parse_alert(device.status.get("error"))
    if alert is None:
        return None
    return {
        "type": alert.type,
        "code": alert.code,
        "state": alert.state,
        "count": alert.count,
        "unit_id": alert.unit_id,
        "timestamp": alert.timestamp,
        "raw": alert.raw,
    }


@dataclass(frozen=True, kw_only=True)
class MtxSensorDescription(SensorEntityDescription):
    """Describes an MTX status sensor."""

    value_fn: Callable[[MtxDevice], str | None]
    attributes_fn: Callable[[MtxDevice], dict[str, Any] | None] | None = None


SENSORS: tuple[MtxSensorDescription, ...] = (
    MtxSensorDescription(
        key=UID_RUN_MODE,
        translation_key="run_mode",
        device_class=SensorDeviceClass.ENUM,
        options=["normal", "emergency", "update"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.status.get("runmode"),
    ),
    MtxSensorDescription(
        key=UID_ALERT,
        translation_key="alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_alert_state,
        attributes_fn=_alert_attributes,
    ),
    MtxSensorDescription(
        key=UID_SAMPLING_RATE,
        translation_key="sampling_rate",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.status.get("fs"),
    ),
    MtxSensorDescription(
        key=UID_WORD_CLOCK,
        translation_key="word_clock",
        device_class=SensorDeviceClass.ENUM,
        options=["lock", "unlock"],
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.status.get("lockstatus"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MtxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up status sensors."""
    device = entry.runtime_data
    async_add_entities(MtxStatusSensor(device, description) for description in SENSORS)


class MtxStatusSensor(MtxEntity, SensorEntity):
    """A devstatus value."""

    entity_description: MtxSensorDescription

    def __init__(self, device: MtxDevice, description: MtxSensorDescription) -> None:
        """Initialize the sensor."""
        super().__init__(
            device,
            description.key,
            description.translation_key or description.key,
            watch=(KEY_STATUS,),
        )
        self.entity_description = description

    @property
    def native_value(self) -> str | None:
        """Return the status value."""
        value = self.entity_description.value_fn(self._device)
        options = self.entity_description.options
        if options is not None and value not in options:
            return None
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra details."""
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self._device)
