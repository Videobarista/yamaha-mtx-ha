"""Parameter specs: which parameters become which entities.

Pure Python, no Home Assistant imports. Used by the platforms, by the device
(to know what to sync) and by the simulator (to know what exists).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from .const import (
    DEFAULT_OPTIONS,
    OPT_DCA,
    OPT_INPUTS,
    OPT_MATRIX,
    OPT_OUTPUTS,
    OPT_ROUTER,
    OPT_ZONES,
)
from .profiles import DCA_GROUPS, SCHEDULER_ADDRESS, MtxProfile

PLATFORM_NUMBER: Final = "number"
PLATFORM_SWITCH: Final = "switch"
PLATFORM_SELECT: Final = "select"


@dataclass(frozen=True, slots=True)
class ParamSpec:
    """One device parameter exposed as an entity."""

    key: str
    platform: str
    translation_key: str
    address: str
    placeholders: tuple[tuple[str, str], ...] = ()
    name_address: str | None = None
    max_db: float = 10.0
    options: tuple[str, ...] = ()


def build_specs(profile: MtxProfile, options: Mapping[str, object]) -> list[ParamSpec]:
    """Build the parameter specs for the enabled entity groups."""

    def enabled(option: str) -> bool:
        return bool(options.get(option, DEFAULT_OPTIONS[option]))

    specs: list[ParamSpec] = []

    if enabled(OPT_INPUTS):
        for channel in profile.inputs:
            placeholders = (("channel", channel.label),)
            specs.append(
                ParamSpec(
                    f"{channel.key}_level",
                    PLATFORM_NUMBER,
                    "input_level",
                    profile.input_level(channel),
                    placeholders,
                    channel.name_address,
                )
            )
            specs.append(
                ParamSpec(
                    f"{channel.key}_on",
                    PLATFORM_SWITCH,
                    "input_on",
                    profile.input_on(channel),
                    placeholders,
                    channel.name_address,
                )
            )

    if enabled(OPT_ZONES):
        for zone in profile.zones:
            placeholders = (("zone", zone.label),)
            specs.append(
                ParamSpec(
                    f"{zone.key}_level",
                    PLATFORM_NUMBER,
                    "zone_level",
                    profile.zone_level(zone),
                    placeholders,
                    zone.name_address,
                )
            )
            specs.append(
                ParamSpec(
                    f"{zone.key}_on",
                    PLATFORM_SWITCH,
                    "zone_on",
                    profile.zone_on(zone),
                    placeholders,
                    zone.name_address,
                )
            )

    if enabled(OPT_OUTPUTS):
        for output in profile.outputs:
            placeholders = (("output", output.label),)
            specs.append(
                ParamSpec(
                    f"{output.key}_level",
                    PLATFORM_NUMBER,
                    "output_level",
                    profile.output_level(output),
                    placeholders,
                    output.name_address,
                )
            )
            specs.append(
                ParamSpec(
                    f"{output.key}_on",
                    PLATFORM_SWITCH,
                    "output_on",
                    profile.output_on(output),
                    placeholders,
                    output.name_address,
                )
            )

    if enabled(OPT_ROUTER):
        for output in profile.outputs:
            specs.append(
                ParamSpec(
                    f"{output.key}_source",
                    PLATFORM_SELECT,
                    "router",
                    profile.router(output),
                    (("output", output.label),),
                    output.name_address,
                    options=profile.router_options,
                )
            )

    if enabled(OPT_DCA):
        for group, letter in enumerate(DCA_GROUPS):
            placeholders = (("dca", letter),)
            key = letter.lower()
            specs.extend(
                (
                    ParamSpec(
                        f"input_dca_{key}_level",
                        PLATFORM_NUMBER,
                        "input_dca_level",
                        profile.input_dca_level(group),
                        placeholders,
                    ),
                    ParamSpec(
                        f"input_dca_{key}_mute",
                        PLATFORM_SWITCH,
                        "input_dca_mute",
                        profile.input_dca_mute(group),
                        placeholders,
                    ),
                    ParamSpec(
                        f"zone_dca_{key}_level",
                        PLATFORM_NUMBER,
                        "zone_dca_level",
                        profile.zone_dca_level(group),
                        placeholders,
                    ),
                    ParamSpec(
                        f"zone_dca_{key}_mute",
                        PLATFORM_SWITCH,
                        "zone_dca_mute",
                        profile.zone_dca_mute(group),
                        placeholders,
                    ),
                )
            )

    if enabled(OPT_MATRIX):
        for source in profile.matrix_sources:
            for zone in profile.zones:
                placeholders = (("channel", source.label), ("zone", zone.label))
                key = f"xp_{source.key}_{zone.key}"
                specs.append(
                    ParamSpec(
                        f"{key}_level",
                        PLATFORM_NUMBER,
                        "crosspoint_level",
                        profile.crosspoint_level(source, zone),
                        placeholders,
                        source.name_address,
                        max_db=0.0,
                    )
                )
                specs.append(
                    ParamSpec(
                        f"{key}_on",
                        PLATFORM_SWITCH,
                        "crosspoint_on",
                        profile.crosspoint_on(source, zone),
                        placeholders,
                        source.name_address,
                    )
                )

    specs.append(
        ParamSpec("scheduler", PLATFORM_SWITCH, "scheduler", SCHEDULER_ADDRESS)
    )
    return specs
