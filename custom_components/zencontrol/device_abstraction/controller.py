import asyncio
import logging
from typing import Dict, List, Optional
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

class ZenControllerRegistry:
    """Registry for managing ZenControl controllers."""
    
    def __init__(self):
        self.controllers: Dict[str, ZenController] = {}
        
    def add_controller(self, uid: str, ip: str) -> "ZenController":
        """Add or update a controller in the registry."""
        if uid not in self.controllers:
            self.controllers[uid] = ZenController(uid, ip)
            _LOGGER.info("Discovered controller %s (%s)", uid, ip)
        else:
            # Update IP if changed
            if self.controllers[uid].ip != ip:
                _LOGGER.info("Controller %s IP changed from %s to %s", 
                             uid, self.controllers[uid].ip, ip)
                self.controllers[uid].ip = ip
                
        return self.controllers[uid]
    
    def get_controller(self, uid: str) -> Optional["ZenController"]:
        """Get a controller by UID."""
        return self.controllers.get(uid)
    
    def get_ready_controllers(self) -> List["ZenController"]:
        """Get all ready controllers."""
        return [c for c in self.controllers.values() if c.is_ready]
    
    def remove_stale_controllers(self, timeout: float = 30):
        """Remove controllers that haven't been seen within timeout."""
        now = asyncio.get_event_loop().time()
        stale = [uid for uid, c in self.controllers.items() 
                 if now - c.last_seen > timeout]
        for uid in stale:
            _LOGGER.warning("Removing stale controller %s", uid)
            del self.controllers[uid]

class ZenController:
    """Representation of a ZenControl appliance."""
    
    def __init__(self, uid: str, ip: str, hass: Optional[HomeAssistant] = None):
        self.uid = uid
        self.ip = ip
        self.hass = hass
        self.is_ready = False
        self.last_seen = asyncio.get_event_loop().time()
        self.devices: Dict[str, ZenDevice] = {}
        
    def register_hass(self, hass: HomeAssistant):
        """Set Home Assistant instance reference."""
        self.hass = hass
        for device in self.devices.values():
            device.register_hass(hass)
        
    def update_heartbeat(self):
        """Update last seen timestamp."""
        self.last_seen = asyncio.get_event_loop().time()
        
    def mark_ready(self):
        """Mark controller as ready."""
        if not self.is_ready:
            self.is_ready = True
            _LOGGER.info("Controller %s (%s) ready", self.uid, self.ip)
            
    def add_device(self, device: "ZenDevice"):
        """Add a device to this controller."""
        if self.hass:
            device.register_hass(self.hass)
        self.devices[device.device_id] = device
        
    def get_device(self, device_id: str) -> Optional["ZenDevice"]:
        """Get a device by ID."""
        return self.devices.get(device_id)
        
    async def send_command(self, command: dict):
        """Send a command to the controller."""
        # This would be implemented using the UDP protocol
        # For now, it's a placeholder
        _LOGGER.debug("Sending command to %s: %s", self.uid, command)
        return True