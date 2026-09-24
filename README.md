# Yamaha MTX for Home Assistant

[![Validate](https://github.com/Videobarista/yamaha-mtx-ha/actions/workflows/validate.yml/badge.svg)](https://github.com/Videobarista/yamaha-mtx-ha/actions/workflows/validate.yml)
[![CodeQL](https://github.com/Videobarista/yamaha-mtx-ha/actions/workflows/codeql.yml/badge.svg)](https://github.com/Videobarista/yamaha-mtx-ha/actions/workflows/codeql.yml)
[![Ruff check](https://github.com/Videobarista/yamaha-mtx-ha/actions/workflows/ruff.yml/badge.svg)](https://github.com/Videobarista/yamaha-mtx-ha/actions/workflows/ruff.yml)
[![hassfest](https://img.shields.io/github/actions/workflow/status/Videobarista/yamaha-mtx-ha/validate.yml?label=hassfest&logo=homeassistant)](https://github.com/Videobarista/yamaha-mtx-ha/actions/workflows/validate.yml)
[![HACS validation](https://img.shields.io/github/actions/workflow/status/Videobarista/yamaha-mtx-ha/validate.yml?label=HACS%20validation)](https://github.com/Videobarista/yamaha-mtx-ha/actions/workflows/validate.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GitHub release](https://img.shields.io/github/v/release/Videobarista/yamaha-mtx-ha?include_prereleases&sort=semver)](https://github.com/Videobarista/yamaha-mtx-ha/releases)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Videobarista&repository=yamaha-mtx-ha&category=integration)

Control Yamaha **MTX3** and **MTX5-D** matrix processors from Home Assistant:
input channels, zones, outputs, the output router, DCA groups, matrix
crosspoints and presets. Changes made on the device, in MTX-MRX Editor, on a
DCP wall panel or by another controller show up in Home Assistant right away
(local push, no polling).

The integration talks to the processor over the Yamaha remote control protocol
(RCP, TCP port 49280) and was built from Yamaha's official RCP specification
V4.0.0 for MTX/MRX/XMV/EXi8/EXo8.

> This project is not affiliated with, endorsed by or supported by Yamaha
> Corporation. Yamaha, MTX and MTX-MRX Editor are trademarks of Yamaha
> Corporation.

## Features

- Config flow (UI setup), reconfigure (new IP address) and options.
- Built-in **simulator**: try everything without hardware (see below).
- Push updates for every tracked parameter, automatic reconnect and a full
  resync after preset recalls or an MTX-MRX Editor synchronisation.
- Calm when the MTX is off: a connection sensor shows the state, Home
  Assistant starts normally and picks the device up when it comes back.
- Channel names from MTX-MRX Editor as the `channel_name` attribute.
- Preset recall with the current preset and its "modified" state.
- Two actions: `set_crosspoint` and `send_command` (raw RCP with response).
- Diagnostics download, English and Dutch translations.

## Supported devices

| Model  | Inputs                               | Zones | Outputs |
| ------ | ------------------------------------ | ----- | ------- |
| MTX3   | CH 1-16, ST IN 1L-3R, FX RTN 1L-2R   | 8     | 8       |
| MTX5-D | CH 1-24, ST IN 1L-3R, FX RTN 1L-2R   | 16    | 16      |

The model is detected when you add the device. Other devices are refused
with a clear message.

## Installation

### HACS (custom repository)

1. In Home Assistant open **HACS** → menu (⋮) → **Custom repositories**.
2. Repository: `https://github.com/Videobarista/yamaha-mtx-ha`,
   type: **Integration** → **Add**.
3. Search for **Yamaha MTX**, download it and restart Home Assistant.

### Manual

Copy `custom_components/yamaha_mtx` into the `custom_components` folder of your
Home Assistant configuration and restart Home Assistant.

## Configuration

**Settings** → **Devices & services** → **Add integration** → **Yamaha MTX**.

| Field | Description                                          |
| ----- | ---------------------------------------------------- |
| Host  | IP address or hostname of the MTX                    |
| Port  | Remote control port, `49280` by default              |

Requirements:

- Home Assistant must reach the MTX on TCP port 49280 (check firewall and
  VLAN rules).
- An MTX accepts up to 8 remote control connections at the same time. Home
  Assistant uses one.

### Simulator

Enter `simulator` (MTX3) or `simulator-mtx5d` (MTX5-D) as host. The
integration then starts a small simulated MTX inside Home Assistant on
127.0.0.1 that speaks the same protocol as the real device, with three example
presets. Use it to build dashboards and automations before the hardware is on
site. Values live in memory and reset when Home Assistant restarts.

When the real MTX arrives, use **Reconfigure** only if it is the same device;
otherwise add it as a new entry and remove the simulator entry.

### Options

Choose which groups of controls become entities:

| Option              | Default | Entities                                         |
| ------------------- | ------- | ------------------------------------------------ |
| Input channels      | on      | Level + on/off per input                         |
| Zones               | on      | Master level + on/off per zone                   |
| Output channels     | on      | Level + on/off per output                        |
| Output router       | on      | Source select per output (NONE, ZONE n, YDIF n)  |
| DCA groups          | off     | Level + mute of input DCA and zone DCA A-H       |
| Matrix crosspoints  | off     | Level + on/off per crosspoint (416 on MTX3, 1088 on MTX5-D) |

Entities of groups that you switch off are removed. The `set_crosspoint`
action works without the crosspoint entities.

## Entities

| Platform | Entity                      | Notes                                                |
| -------- | --------------------------- | ---------------------------------------------------- |
| binary_sensor | Connection             | Connected / disconnected, always available (diagnostic) |
| number   | Channel / zone / output / DCA level | dB, slider -80 to +10 dB                     |
| number   | Crosspoint level            | dB, slider -80 to 0 dB                               |
| switch   | Channel / zone / output on  | On = signal passes (Yamaha "ON" key)                 |
| switch   | DCA mute                    | On = muted                                           |
| switch   | Crosspoint                  | On = crosspoint active                               |
| switch   | Event scheduler             | Enables the MTX event scheduler                      |
| select   | Output source               | Router: NONE, ZONE 1-n, YDIF IN 1-16                 |
| select   | Preset                      | Recall; attributes `preset_number` and `modified`    |
| sensor   | Run mode                    | normal / emergency / update (diagnostic)             |
| sensor   | Alert                       | Latest alert text with details as attributes         |
| sensor   | Sampling rate, Word clock   | Diagnostic, disabled by default                      |
| button   | Resync                      | Reads all values from the device again               |

### Level notes

- Levels are shown and set in dB with 0.5 dB steps.
- The device reports -∞ as **-138.0 dB**. Setting a level never sends -∞;
  use the matching on/off switch to silence a channel.
- If the device limits a value (for example a level above the maximum), it
  answers with the value it actually used and the entity follows it.

## Actions

### `yamaha_mtx.set_crosspoint`

Set the level and/or on state of one crosspoint (input to zone).

```yaml
action: yamaha_mtx.set_crosspoint
data:
  config_entry_id: 01J0EXAMPLEENTRYID
  source: CH 3
  zone: 2
  level: -6
  enabled: true
```

`source` is `CH n`, `ST IN 1L` … `ST IN 3R` or `FX RTN 1L` … `FX RTN 2R`.
Give `level`, `enabled` or both.

### `yamaha_mtx.send_command`

Send one raw RCP command and get the reply line back, including `ERROR`
replies. Handy for parameters that have no entity (EQ, dynamics, ducker,
ANC and more; see the Yamaha RCP specification for addresses).

```yaml
action: yamaha_mtx.send_command
data:
  config_entry_id: 01J0EXAMPLEENTRYID
  command: get MTX:mem_512/60000/0/0/0/0/0 0 0
response_variable: mtx_reply
```

Response:

```yaml
command: get MTX:mem_512/60000/0/0/0/0/0 0 0
reply: OK get MTX:mem_512/60000/0/0/0/0/0 0 0 -1000
```

A `set` sent this way also updates the matching entity.

## Power and offline behaviour

The MTX has no remote power, standby or Wake-on-LAN function in its control
protocol (only Yamaha XMV amplifiers have a standby parameter). To switch the
processor on and off from Home Assistant, use a switched PDU, smart plug or
relay on its mains supply.

The integration is built for that:

- Home Assistant starts normally while the MTX is off. All entities exist but
  are unavailable, and the **Connection** sensor shows *Disconnected*.
- One warning is logged when the connection fails; after that it retries
  quietly every 5 to 60 seconds.
- As soon as the MTX answers again, all values are read and the entities
  become available.

## How it works

- After connecting, the integration waits until the MTX reports run mode
  `normal`, sets the session to UTF-8 and raw values and asks the device to
  keep the session open. A status query every 10 seconds keeps it alive.
- All tracked values are read once, after that the device pushes changes.
- After a preset recall, a return to normal run mode or an MTX-MRX Editor
  synchronisation, everything is read again.
- If the connection drops, entities become unavailable and the integration
  reconnects with a growing delay (5 to 60 seconds).
- If a different device answers at the configured address (other serial
  number or model), it is refused and a warning is logged.
- If the device rejects a parameter, that entity becomes unavailable and a
  warning is logged; the rest keeps working.

## Other Yamaha devices

- **MRX7-D**: same protocol, but the MRX7-D is freely configurable. It is
  controlled through the Remote Control Setup List made in MTX-MRX Editor,
  which the device does not describe over the network. Not supported yet.
- **XMV, EXi8/EXo8**: same protocol family, different parameter map. Not
  supported.
- **TF, DM3, CL, QL, RIVAGE PM** mixing consoles: they use the same transport
  (TCP 49280, `get`/`set`/`NOTIFY`) but a completely different set of
  parameter addresses. Not supported by this integration.

## Limitations

- Only MTX3 and MTX5-D.
- Level meters are not implemented.
- EQ, dynamics, ducker, ANC and other processing blocks have no entities; use
  `send_command` for those.
- Preset names are read at startup and after an MTX-MRX Editor
  synchronisation.

## Troubleshooting

- **Cannot connect**: check the IP address, that TCP port 49280 is reachable
  from Home Assistant and that no more than 8 controllers are connected.
- **Entities stay unavailable**: check the Connection sensor. If it shows
  *Connected*, the MTX may be in emergency or update mode; the run mode sensor
  shows which.
- **Debug logging**:

  ```yaml
  logger:
    logs:
      custom_components.yamaha_mtx: debug
  ```

- **Diagnostics**: device page → ⋮ → **Download diagnostics** (host and
  serial number are redacted).

## License

[MIT](LICENSE) © Videobarista
