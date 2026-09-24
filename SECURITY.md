# Security Policy

## Supported versions

Only the latest release receives fixes.

| Version | Supported |
| ------- | --------- |
| 0.1.x   | Yes       |

## Reporting a vulnerability

Please report security issues privately through GitHub:
**Security** tab of this repository → **Report a vulnerability**.
Do not open a public issue for security problems.

You can expect a first reply within a week.

## Deployment notes

- The Yamaha remote control protocol (RCP, TCP port 49280) is plain text and
  has no authentication or encryption. Anyone who can reach that port can
  control the processor. Keep the MTX on a trusted network segment (for example
  a dedicated AV or IoT VLAN) and do not expose port 49280 to the internet.
- The `yamaha_mtx.send_command` action passes raw commands to the device.
  Only Home Assistant administrators can call it from the UI, but automations
  and scripts can as well: review what you give access to your instance.
- The integration stores only host and port in the config entry. No
  credentials are involved.
