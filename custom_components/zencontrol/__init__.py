import asyncio
import logging
import voluptuous as vol
from typing import Any, Dict, Optional

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers import config_validation as cv

# Import const first to ensure DOMAIN is defined
from .const import DOMAIN, DEFAULT_MULTICAST_GROUP, DEFAULT_MULTICAST_PORT, DEFAULT_UDP_PORT, DEFAULT_DISCOVERY_TIMEOUT
from .config_flow import ZenControlConfigFlow
from .hub import ZenControlHub, DISCOVERY_SIGNAL
from .discovery_manager import DiscoveryManager

# Default values moved to const
DEFAULT_MULTICAST_GROUP = "239.255.90.67"
DEFAULT_MULTICAST_PORT = 5110
DEFAULT_UDP_PORT = 5108
DEFAULT_DISCOVERY_TIMEOUT = 30

_LOGGER = logging.getLogger(__name__)

# Configuration schema for YAML-based configuration
CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Optional("multicast_group", default=DEFAULT_MULTICAST_GROUP): str,
        vol.Optional("multicast_port", default=DEFAULT_MULTICAST_PORT): cv.port,
        vol.Optional("udp_port", default=DEFAULT_UDP_PORT): cv.port,
        vol.Optional("discovery_timeout", default=DEFAULT_DISCOVERY_TIMEOUT): vol.All(
            cv.positive_int, vol.Range(min=5, max=300)
        ),
    })
}, extra=vol.ALLOW_EXTRA)

async def async_setup(hass: HomeAssistant, config: Dict[str, Any]) -> bool:
    """Set up the ZenControl component from YAML configuration."""
    if DOMAIN not in config:
        return True
        
    conf = config[DOMAIN]
    
    # Check if we've already imported the config
    if not any(entry.source == config_entries.SOURCE_IMPORT 
               for entry in hass.config_entries.async_entries(DOMAIN)):
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_IMPORT},
                data=conf,
            )
        )
    
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ZenControl from a config entry."""
    # Create hub instance with config entry
    hub = ZenControlHub(hass, entry)
    
    # Start communication layers
    try:
        await hub.start()
    except Exception as e:
        _LOGGER.error("Failed to start communication layers: %s", e)
        return False
    
    # Setup discovery manager
    hub.discovery_manager = DiscoveryManager(hass, hub)
    
    # Store hub reference
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = hub
    
    # Setup platforms
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setups(
            entry, ["light", "switch", "binary_sensor"]
        )
    )
    
    # Register services
    await _register_services(hass, hub, entry)
    
    # Setup discovery signal handler
    entry.async_on_unload(
        async_dispatcher_connect(
            hass, 
            DISCOVERY_SIGNAL, 
            hub.handle_discovery_event
        )
    )
    
    # Start periodic tasks
    entry.async_on_unload(
        asyncio.create_task(hub.controller_watchdog())
    )
    
    # Trigger initial discovery for controllers with discovery enabled
    await hub.discovery_manager.start_discovery(user_initiated=False)
    
    # Log successful setup
    _LOGGER.info("ZenControl integration setup complete with %d controllers", 
                 len(hub.registry.controllers))
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, ["light", "switch", "binary_sensor"]
    )
    
    if unload_ok and DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        # Stop hub and cleanup
        hub = hass.data[DOMAIN].pop(entry.entry_id)
        try:
            await hub.stop()
        except Exception as e:
            _LOGGER.error("Error during shutdown: %s", e)
        
    return unload_ok

async def _register_services(hass: HomeAssistant, hub: "ZenControlHub", entry: ConfigEntry):
    """Register ZenControl services."""
    from .device_abstraction.devices import ZenSwitch
    
    async def handle_discover_devices(call):
        """Handle discover devices service call."""
        force_reset = call.data.get("force_reset", False)
        if force_reset:
            hub.devices.clear()
            _LOGGER.info("Cleared existing devices")
        await hub.discovery_manager.start_discovery(user_initiated=True)
        
    hass.services.async_register(
        DOMAIN, "discover_devices", handle_discover_devices
    )
    
    async def handle_device_command(call):
        """Handle generic device command."""
        device_id = call.data.get("device_id")
        command = call.data.get("command")
        params = call.data.get("params", {})
        
        if not device_id:
            _LOGGER.error("Missing device_id in service call")
            return
            
        if device := hub.get_device(device_id):
            if hasattr(device, command):
                try:
                    await getattr(device, command)(**params)
                    _LOGGER.debug("Executed command %s on device %s", command, device_id)
                except Exception as e:
                    _LOGGER.error("Error executing command %s on device %s: %s", 
                                 command, device_id, e)
            else:
                _LOGGER.error("Device %s has no command '%s'", device_id, command)
        else:
            _LOGGER.error("Device not found: %s", device_id)
                
    hass.services.async_register(
        DOMAIN, "device_command", handle_device_command
    )
    
    async def handle_assign_scene(call):
        """Assign a scene to a switch button."""
        device_id = call.data.get("device_id")
        button = call.data.get("button")
        scene_id = call.data.get("scene_id")
        
        if not device_id or button is None or not scene_id:
            _LOGGER.error("Missing parameters in assign_scene service call")
            return
            
        if device := hub.get_device(device_id):
            if isinstance(device, ZenSwitch):
                try:
                    device.assign_scene(button, scene_id)
                    _LOGGER.info("Assigned scene %s to button %d on device %s", 
                                scene_id, button, device_id)
                except Exception as e:
                    _LOGGER.error("Error assigning scene: %s", e)
            else:
                _LOGGER.error("Device %s is not a switch", device_id)
        else:
            _LOGGER.error("Device not found: %s", device_id)
                
    hass.services.async_register(
        DOMAIN, "assign_scene", handle_assign_scene
    )

    async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
        """Migrate old entry."""
        _LOGGER.debug("Migrating from version %s", config_entry.version)
        
        if config_entry.version == 1:
            # Migrate from version 1 (single controller) to version 2 (multi-controller)
            new_data = {
                "network": {
                    "multicast_group": config_entry.data.get("multicast_group", DEFAULT_MULTICAST_GROUP),
                    "multicast_port": config_entry.data.get("multicast_port", DEFAULT_MULTICAST_PORT),
                    "udp_port": config_entry.data.get("udp_port", DEFAULT_UDP_PORT)
                },
                "controllers": {
                    "zc-main": {
                        "ip_address": config_entry.data.get("controller_ip", "192.168.1.100"),
                        "name": "Main Controller",
                        "discovery_enabled": True
                    }
                }
            }
            
            config_entry.version = 2
            hass.config_entries.async_update_entry(config_entry, data=new_data)
            _LOGGER.info("Migration to version 2 successful")
        
        return True