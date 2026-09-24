"""Model profiles for MTX3 and MTX5-D.

All addresses come from section 7.1 of the Yamaha RCP specification V4.0.0
(MemNo 512). Pure Python, no Home Assistant imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .protocol import param_address

SCHEDULER_ADDRESS: Final = "MTX:EvntScd_On"
DCA_GROUPS: Final = ("A", "B", "C", "D", "E", "F", "G", "H")

# Unique ids (spec section 7.1).
UID_INPUT_LEVEL: Final = 60000  # element 0 = channel fader, element 2 = DCA master
UID_INPUT_ON: Final = 60001  # element 0 = channel on, element 2 = DCA master mute
UID_ZONE_LEVEL: Final = 60002
UID_ZONE_ON: Final = 60003
UID_MATRIX: Final = 30002  # element 1, prm 0 = level, prm 1 = on
UID_NAME_INPUT: Final = 70000
UID_NAME_ZONE: Final = 70001
UID_NAME_OUTPUT: Final = 70002
UID_NAME_INPUT_17_24: Final = 70003
UID_NAME_STEREO_FX: Final = 70004
UID_NAME_ZONE_9_16: Final = 70005
UID_NAME_OUTPUT_9_16: Final = 70006


@dataclass(frozen=True, slots=True)
class Channel:
    """A channel of the device.

    index is the X (inputs) or Y (zones) position used in addresses.
    """

    key: str
    label: str
    index: int
    name_address: str | None = None


@dataclass(frozen=True, slots=True)
class MtxProfile:
    """Parameter map of one model."""

    model: str
    inputs: tuple[Channel, ...]
    fx_returns: tuple[Channel, ...]
    zones: tuple[Channel, ...]
    outputs: tuple[Channel, ...]
    output_uid: int
    router_uid: int
    router_options: tuple[str, ...]

    @property
    def matrix_sources(self) -> tuple[Channel, ...]:
        """Return all matrix inputs (input channels and effect returns)."""
        return self.inputs + self.fx_returns

    def matrix_source(self, label: str) -> Channel:
        """Return a matrix source by its label, e.g. 'CH 1' or 'ST IN 2R'."""
        wanted = label.strip().upper()
        for channel in self.matrix_sources:
            if channel.label.upper() == wanted:
                return channel
        raise ValueError(f"{self.model} has no matrix source '{label}'")

    def zone(self, number: int) -> Channel:
        """Return a zone by its 1-based number."""
        if not 1 <= number <= len(self.zones):
            raise ValueError(f"{self.model} has no zone {number}")
        return self.zones[number - 1]

    # Address helpers --------------------------------------------------------

    @staticmethod
    def input_level(channel: Channel) -> str:
        """Input channel fader level."""
        return param_address(UID_INPUT_LEVEL, 0, channel.index)

    @staticmethod
    def input_on(channel: Channel) -> str:
        """Input channel on/off."""
        return param_address(UID_INPUT_ON, 0, channel.index)

    @staticmethod
    def zone_level(zone: Channel) -> str:
        """Zone output master fader level."""
        return param_address(UID_ZONE_LEVEL, 0, zone.index)

    @staticmethod
    def zone_on(zone: Channel) -> str:
        """Zone output master on/off."""
        return param_address(UID_ZONE_ON, 0, zone.index)

    def output_level(self, output: Channel) -> str:
        """Output channel fader level."""
        return param_address(self.output_uid, 0, output.index)

    def output_on(self, output: Channel) -> str:
        """Output channel on/off."""
        return param_address(self.output_uid, 1, output.index)

    def router(self, output: Channel) -> str:
        """Router source of an output channel."""
        return param_address(self.router_uid, 1, 0, output.index)

    @staticmethod
    def input_dca_level(group: int) -> str:
        """Input DCA group master level (group 0-7 = A-H)."""
        return param_address(UID_INPUT_LEVEL, 2, 0, group)

    @staticmethod
    def input_dca_mute(group: int) -> str:
        """Input DCA group master mute."""
        return param_address(UID_INPUT_ON, 2, 0, group)

    @staticmethod
    def zone_dca_level(group: int) -> str:
        """Zone DCA group master level."""
        return param_address(UID_ZONE_LEVEL, 2, 0, group)

    @staticmethod
    def zone_dca_mute(group: int) -> str:
        """Zone DCA group master mute."""
        return param_address(UID_ZONE_ON, 2, 0, group)

    @staticmethod
    def crosspoint_level(source: Channel, zone: Channel) -> str:
        """Matrix send level from a source to a zone."""
        return param_address(UID_MATRIX, 1, source.index, zone.index, 0)

    @staticmethod
    def crosspoint_on(source: Channel, zone: Channel) -> str:
        """Matrix send on/off from a source to a zone."""
        return param_address(UID_MATRIX, 1, source.index, zone.index, 1)


def _name(unique_id: int, x_pos: int) -> str:
    return param_address(unique_id, 0, x_pos)


def _mono(number: int, index: int, name_address: str) -> Channel:
    return Channel(f"ch{number}", f"CH {number}", index, name_address)


def _stereo_inputs(first_index: int) -> tuple[Channel, ...]:
    channels = []
    for offset, suffix in enumerate(("1L", "1R", "2L", "2R", "3L", "3R")):
        channels.append(
            Channel(
                f"stin{suffix.lower()}",
                f"ST IN {suffix}",
                first_index + offset,
                _name(UID_NAME_STEREO_FX, offset),
            )
        )
    return tuple(channels)


def _fx_returns(first_index: int) -> tuple[Channel, ...]:
    channels = []
    for offset, suffix in enumerate(("1L", "1R", "2L", "2R")):
        # One name per stereo effect return (x 6 = FX RTN 1, x 7 = FX RTN 2).
        channels.append(
            Channel(
                f"fxrtn{suffix.lower()}",
                f"FX RTN {suffix}",
                first_index + offset,
                _name(UID_NAME_STEREO_FX, 6 + offset // 2),
            )
        )
    return tuple(channels)


def _split_name(first_uid: int, second_uid: int, index: int) -> str:
    """Name address for channels 1-8 (first uid) and 9-16 (second uid)."""
    if index < 8:
        return _name(first_uid, index)
    return _name(second_uid, index - 8)


def _zones(count: int) -> tuple[Channel, ...]:
    return tuple(
        Channel(
            f"zone{index + 1}",
            str(index + 1),
            index,
            _split_name(UID_NAME_ZONE, UID_NAME_ZONE_9_16, index),
        )
        for index in range(count)
    )


def _outputs(count: int) -> tuple[Channel, ...]:
    return tuple(
        Channel(
            f"out{index + 1}",
            str(index + 1),
            index,
            _split_name(UID_NAME_OUTPUT, UID_NAME_OUTPUT_9_16, index),
        )
        for index in range(count)
    )


def _router_options(zones: int) -> tuple[str, ...]:
    """Router values (spec 6.2.5.1): NONE, ZONE 1..n, YDIF IN 1..16."""
    return (
        ("NONE",)
        + tuple(f"ZONE {number}" for number in range(1, zones + 1))
        + tuple(f"YDIF IN {number}" for number in range(1, 17))
    )


def _build_mtx3() -> MtxProfile:
    # X positions: 0-7 CH1-8, 8-13 ST IN 1L-3R, 14-21 CH9-16, 22-25 FX RTN.
    inputs = (
        tuple(_mono(n, n - 1, _name(UID_NAME_INPUT, n - 1)) for n in range(1, 9))
        + _stereo_inputs(8)
        + tuple(_mono(n, n + 5, _name(UID_NAME_INPUT, n - 1)) for n in range(9, 17))
    )
    return MtxProfile(
        model="MTX3",
        inputs=inputs,
        fx_returns=_fx_returns(22),
        zones=_zones(8),
        outputs=_outputs(8),
        output_uid=20017,
        router_uid=20016,
        router_options=_router_options(8),
    )


def _build_mtx5d() -> MtxProfile:
    # X positions: 0-15 CH1-16, 16-21 ST IN 1L-3R, 22-29 CH17-24, 30-33 FX RTN.
    inputs = (
        tuple(_mono(n, n - 1, _name(UID_NAME_INPUT, n - 1)) for n in range(1, 17))
        + _stereo_inputs(16)
        + tuple(
            _mono(n, n + 5, _name(UID_NAME_INPUT_17_24, n - 17)) for n in range(17, 25)
        )
    )
    return MtxProfile(
        model="MTX5-D",
        inputs=inputs,
        fx_returns=_fx_returns(30),
        zones=_zones(16),
        outputs=_outputs(16),
        output_uid=20024,
        router_uid=20023,
        router_options=_router_options(16),
    )


PROFILES: Final[dict[str, MtxProfile]] = {
    "MTX3": _build_mtx3(),
    "MTX5-D": _build_mtx5d(),
}


def get_profile(model: str) -> MtxProfile | None:
    """Return the profile for a product name as reported by 'devinfo productname'."""
    normalized = model.strip().upper().replace(" ", "")
    for name, profile in PROFILES.items():
        if name.replace("-", "") == normalized.replace("-", ""):
            return profile
    return None
