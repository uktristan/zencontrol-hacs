# ZenControl Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Integrate ZenControl lighting systems with Home Assistant.

## Features
- Control DALI lights (white & color)
- Receive real-time button press events
- Motion and occupancy sensing
- Multicast-based event system

## Installation
1. Install [HACS](https://hacs.xyz)
2. Add this repository as a custom repository
3. Install "ZenControl" integration
4. Restart Home Assistant
5. Add via **Configuration > Devices & Services > Add Integration**

## Configuration
```yaml
# Example advanced configuration
zencontrol:
  multicast_group: "239.255.90.67"
  multicast_port: 5110
  udp_port: 5108
  discovery_timeout: 30