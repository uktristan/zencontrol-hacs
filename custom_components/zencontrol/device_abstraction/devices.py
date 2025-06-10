import asyncio
import logging
from typing import Callable, Dict, List, Optional, Tuple, Any, Set
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

class ZenDevice:
    """Base class for all ZenControl devices."""
    
    def __init__(self, device_id: str, controller: "ZenController", name: Optional[str] = None):
        """
        Initialize a ZenControl device.
        
        :param device_id: Unique device identifier
        :param controller: Parent controller instance
        :param name: Friendly name (defaults to device_id)
        """
        self.device_id = device_id
        self.controller = controller
        self.name = name or device_id.replace("_", " ").title()
        self.state: Dict[str, Any] = {}
        self._callbacks: Set[Callable] = set()
        self._hass: Optional[HomeAssistant] = None
        
    def register_hass(self, hass: HomeAssistant):
        """Set Home Assistant instance reference."""
        self._hass = hass
        
    def register_callback(self, callback: Callable):
        """Register a callback to be called when state changes."""
        self._callbacks.add(callback)
        
    def remove_callback(self, callback: Callable):
        """Remove a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
            
    def notify_callbacks(self):
        """Notify all registered callbacks."""
        for callback in self._callbacks:
            callback()
            
    def update_state(self, new_state: dict):
        """Update device state and notify listeners."""
        changed = False
        for key, value in new_state.items():
            if self.state.get(key) != value:
                self.state[key] = value
                changed = True
                
        if changed:
            _LOGGER.debug("Device %s state updated: %s", self.device_id, self.state)
            self.notify_callbacks()
            
    def fire_event(self, event_type: str, event_data: dict):
        """Fire a Home Assistant event."""
        if self._hass is None:
            return
            
        full_data = {
            "device_id": self.device_id,
            "controller_id": self.controller.uid,
            **event_data
        }
        
        self._hass.bus.async_fire(f"zencontrol_{event_type}", full_data)
        
    async def send_command(self, command: str, params: Optional[dict] = None):
        """Send a command to the device."""
        raise NotImplementedError("Subclasses must implement send_command")


class ZenLight(ZenDevice):
    """Representation of a ZenControl light (both white and color)."""
    
    def __init__(self, device_id: str, controller: "ZenController", is_color: bool = False, name: Optional[str] = None):
        """
        Initialize a ZenControl light.
        
        :param is_color: True if light supports color, False for white only
        """
        super().__init__(device_id, controller, name)
        self.is_color = is_color
        self.state.update({
            "state": "off",
            "brightness": 0,
            "color_temp": None,
            "rgb_color": None,
            "supported_features": []
        })
        
        if self.is_color:
            self.state["rgb_color"] = [255, 255, 255]
            self.state["supported_features"].extend(["RGB", "COLOR_TEMP"])
        else:
            self.state["supported_features"].append("BRIGHTNESS")
            
    async def turn_on(self, **kwargs):
        """Turn the light on with optional parameters."""
        command = {
            "command": "LIGHT_ON",
            "device_id": self.device_id,
            **kwargs
        }
        await self.controller.send_command(command)
        
        # Update local state optimistically
        new_state = {"state": "on"}
        if "brightness" in kwargs:
            new_state["brightness"] = kwargs["brightness"]
        if "rgb_color" in kwargs:
            new_state["rgb_color"] = kwargs["rgb_color"]
        if "color_temp" in kwargs:
            new_state["color_temp"] = kwargs["color_temp"]
            
        self.update_state(new_state)
        
    async def turn_off(self, **kwargs):
        """Turn the light off."""
        await self.controller.send_command({
            "command": "LIGHT_OFF",
            "device_id": self.device_id
        })
        self.update_state({"state": "off"})
        
    async def set_brightness(self, brightness: int):
        """Set light brightness (0-255)."""
        await self.turn_on(brightness=brightness)
        
    async def set_rgb_color(self, rgb: Tuple[int, int, int]):
        """Set RGB color value."""
        if not self.is_color:
            _LOGGER.warning("Attempted to set color on non-color light %s", self.device_id)
            return
            
        await self.turn_on(rgb_color=rgb)
        
    async def set_color_temp(self, color_temp: int):
        """Set color temperature in mireds."""
        if not self.is_color:
            _LOGGER.warning("Attempted to set color temp on non-color light %s", self.device_id)
            return
            
        await self.turn_on(color_temp=color_temp)


class ZenSwitch(ZenDevice):
    """Representation of a ZenControl multi-button switch."""
    
    def __init__(
        self, 
        device_id: str, 
        controller: "ZenController", 
        num_buttons: int = 4, 
        mode: str = "momentary",
        name: Optional[str] = None
    ):
        """
        Initialize a multi-button switch.
        
        :param num_buttons: Number of buttons on the switch
        :param mode: 'momentary' (press/release) or 'toggle' (on/off)
        """
        super().__init__(device_id, controller, name)
        self.num_buttons = num_buttons
        self.mode = mode
        self.button_states: Dict[int, bool] = {}
        self._assigned_scenes: Dict[int, str] = {}  # Button index to scene ID
        
        # Initialize button states
        for i in range(num_buttons):
            self.button_states[i] = False
            
    def handle_button_event(self, button: int, action: str):
        """Handle incoming button event from multicast."""
        _LOGGER.info("Switch %s button %d: %s", self.device_id, button, action)
        
        # Validate button index
        if button < 0 or button >= self.num_buttons:
            _LOGGER.error("Invalid button index %d for switch %s", button, self.device_id)
            return
            
        # Update state based on mode
        if self.mode == "toggle":
            if action == "press":
                self.button_states[button] = not self.button_states[button]
            elif action == "double_press":
                # Double press always toggles
                self.button_states[button] = not self.button_states[button]
        elif self.mode == "momentary":
            # Momentary switches don't maintain state
            if action == "press":
                self.button_states[button] = True
            elif action == "release":
                self.button_states[button] = False
                
        # Notify state change
        self.update_state({"button_states": self.button_states.copy()})
        
        # Fire event for automations
        self.fire_event("button_event", {
            "button": button,
            "action": action,
            "state": self.button_states[button]
        })
        
    async def press_button(self, button: int, action: str = "press"):
        """Simulate button press from HA."""
        # Validate button index
        if button < 0 or button >= self.num_buttons:
            _LOGGER.error("Invalid button index %d for switch %s", button, self.device_id)
            return
            
        # Send command to controller
        await self.controller.send_command({
            "command": "BUTTON_ACTION",
            "device_id": self.device_id,
            "button": button,
            "action": action
        })
        
        # Update local state immediately
        self.handle_button_event(button, action)
        
    def assign_scene(self, button: int, scene_id: str):
        """Assign a scene to a button."""
        if button < 0 or button >= self.num_buttons:
            _LOGGER.error("Invalid button index %d for switch %s", button, self.device_id)
            return
            
        self._assigned_scenes[button] = scene_id
        
    def get_assigned_scene(self, button: int) -> Optional[str]:
        """Get scene assigned to a button."""
        return self._assigned_scenes.get(button)
        
    async def activate_scene(self, button: int):
        """Activate the scene assigned to a button."""
        scene_id = self.get_assigned_scene(button)
        if not scene_id:
            _LOGGER.warning("No scene assigned to button %d on switch %s", button, self.device_id)
            return
            
        if self._hass is None:
            _LOGGER.error("Home Assistant not registered for device %s", self.device_id)
            return
            
        await self._hass.services.async_call(
            "scene",
            "turn_on",
            {"entity_id": scene_id}
        )


class ZenSensor(ZenDevice):
    """Representation of a ZenControl sensor (motion or occupancy)."""
    
    def __init__(
        self, 
        device_id: str, 
        controller: "ZenController", 
        sensor_type: str = "motion",
        name: Optional[str] = None
    ):
        """
        Initialize a ZenControl sensor.
        
        :param sensor_type: 'motion' or 'occupancy'
        """
        super().__init__(device_id, controller, name)
        self.sensor_type = sensor_type
        self.state.update({
            "active": False,
            "last_triggered": None
        })
        
    def handle_motion(self, active: bool):
        """Handle motion detection event."""
        if self.sensor_type != "motion":
            _LOGGER.warning("Received motion event for non-motion sensor %s", self.device_id)
            return
            
        self.update_state({
            "active": active,
            "last_triggered": asyncio.get_event_loop().time() if active else None
        })
        
        # Fire event
        self.fire_event("motion_event", {"active": active})
        
    def handle_occupancy(self, active: bool):
        """Handle occupancy detection event."""
        if self.sensor_type != "occupancy":
            _LOGGER.warning("Received occupancy event for non-occupancy sensor %s", self.device_id)
            return
            
        self.update_state({
            "active": active,
            "last_triggered": asyncio.get_event_loop().time() if active else None
        })
        
        # Fire event
        self.fire_event("occupancy_event", {"active": active})


class ZenController:
    """Representation of a ZenControl appliance (bridge to DALI network)."""
    
    def __init__(self, uid: str, ip: str, hass: Optional[HomeAssistant] = None):
        """
        Initialize a ZenControl controller.
        
        :param uid: Unique controller identifier
        :param ip: IP address of the controller
        """
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
            
    def add_device(self, device: ZenDevice):
        """Add a device to this controller."""
        if self.hass:
            device.register_hass(self.hass)
            
        self.devices[device.device_id] = device
        
    def get_device(self, device_id: str) -> Optional[ZenDevice]:
        """Get a device by ID."""
        return self.devices.get(device_id)
        
    async def send_command(self, command: dict):
        """Send a command to the controller (dummy implementation)."""
        _LOGGER.debug("Sending command to %s: %s", self.uid, command)
        # In real implementation, this would send via UDP
        # For now, just log and simulate success
        
        # Simulate network delay
        await asyncio.sleep(0.05)
        
        # For lights, simulate state change
        if command.get("command") in ["LIGHT_ON", "LIGHT_OFF"]:
            device_id = command["device_id"]
            if device := self.get_device(device_id):
                if command["command"] == "LIGHT_ON":
                    device.update_state({
                        "state": "on",
                        "brightness": command.get("brightness", 255)
                    })
                else:
                    device.update_state({"state": "off"})
                    
        return True