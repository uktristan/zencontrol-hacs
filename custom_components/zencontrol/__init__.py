import asyncio
import logging
import voluptuous as vol
from typing import Any, Dict, Optional

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers import config_validation as cv

# Import config flow first to ensure DOMAIN is registered
from .config_flow import ZenControlConfigFlow

_LOGGER = logging.getLogger(__name__)

DOMAIN = "zencontrol"

# Default configuration values
DEFAULT_MULTICAST_GROUP = "239.255.90.67"
DEFAULT_MULTICAST_PORT = 5110
DEFAULT_UDP_PORT = 5108
DEFAULT_DISCOVERY_TIMEOUT = 30

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
    # Import the rest of the components here to avoid circular imports
    from .discovery_manager import DiscoveryManager, DISCOVERY_SIGNAL
    from .device_abstraction.comms.udp_protocol import ZenUDPProtocol
    from .device_abstraction.comms.multicast_protocol import ZenMulticastProtocol
    from .device_abstraction.controller import ZenControllerRegistry, ZenController
    from .device_abstraction.devices import ZenDevice, ZenLight, ZenSwitch, ZenSensor
    from .hub import ZenControlHub
    
    # Validate multicast address first
    multicast_group = entry.data.get("multicast_group", DEFAULT_MULTICAST_GROUP)
    if not await ZenControlConfigFlow._validate_multicast(multicast_group):
        _LOGGER.error("Invalid multicast group in config: %s", multicast_group)
        return False
        
    # Get configuration from entry
    multicast_port = entry.data.get("multicast_port", DEFAULT_MULTICAST_PORT)
    udp_port = entry.data.get("udp_port", DEFAULT_UDP_PORT)
    discovery_timeout = entry.options.get("discovery_timeout", DEFAULT_DISCOVERY_TIMEOUT)
    
    # Create hub instance
    hub = ZenControlHub(
        hass,
        multicast_group=multicast_group,
        multicast_port=multicast_port,
        udp_port=udp_port,
        discovery_timeout=discovery_timeout
    )
    
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
    
    # Trigger initial discovery
    await hub.discovery_manager.start_discovery(user_initiated=False)
    
    # Log successful setup
    _LOGGER.info("ZenControl integration setup complete")
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