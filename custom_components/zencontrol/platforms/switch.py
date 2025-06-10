import logging
from homeassistant.components.switch import SwitchEntity, SwitchDeviceClass
from homeassistant.helpers.dispatcher import async_dispatcher_connect

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up ZenControl switches from a config entry."""
    hub = hass.data["zencontrol"][config_entry.entry_id]
    
    # Add existing switches
    entities = []
    for device_id, device in hub.devices.items():
        if isinstance(device, ZenSwitch):
            for button_index in range(device.num_buttons):
                entities.append(ZenControlSwitchEntity(device, button_index))
    
    async_add_entities(entities)
    
    # Listen for new device discovery
    async def handle_discovery_event(event):
        """Handle discovery events and add new switches."""
        if "action" not in event or event["action"] != "add":
            return
            
        device_id = event["device_id"]
        device = hub.devices.get(device_id)
        if isinstance(device, ZenSwitch):
            new_entities = []
            for button_index in range(device.num_buttons):
                new_entities.append(ZenControlSwitchEntity(device, button_index))
            if new_entities:
                async_add_entities(new_entities)
    
    async_dispatcher_connect(
        hass, 
        hub.discovery_manager.DISCOVERY_SIGNAL, 
        handle_discovery_event
    )

class ZenControlSwitchEntity(SwitchEntity):
    """Representation of a ZenControl switch button."""
    
    _attr_should_poll = False  # State is updated via multicast events
    _attr_device_class = SwitchDeviceClass.SWITCH
    
    def __init__(self, device: "ZenSwitch", button_index: int):
        """Initialize the switch."""
        self._device = device
        self._button_index = button_index
        self._attr_unique_id = f"{device.device_id}_button_{button_index}"
        self._attr_name = f"{device.name} Button {button_index + 1}"
        self._is_on = False
        
        # Set device info for parent switch
        self._attr_device_info = {
            "identifiers": {("zencontrol", device.device_id)},
            "name": device.name,
            "manufacturer": "ZenControl",
            "model": f"Multi-button Switch ({device.num_buttons} buttons)",
            "via_device": ("zencontrol", device.controller.uid),
        }

    @property
    def is_on(self) -> bool:
        """Return true if switch is on (for toggle mode)."""
        return self._is_on

    async def async_turn_on(self, **kwargs):
        """Turn the switch on (or simulate button press)."""
        await self._device.press_button(self._button_index, "press")
        
        # For toggle mode, update state immediately
        if self._device.mode == "toggle":
            self._is_on = True
            self.async_write_ha_state()
            
        # For momentary mode, turn off after a short delay
        else:
            self._is_on = True
            self.async_write_ha_state()
            await asyncio.sleep(0.3)  # Visual feedback duration
            self._is_on = False
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn the switch off (for toggle mode)."""
        if self._device.mode == "toggle":
            await self._device.press_button(self._button_index, "release")
            self._is_on = False
            self.async_write_ha_state()

    async def async_added_to_hass(self):
        """Register callbacks when entity is added."""
        self._device.register_callback(self._update_callback)
        self._update_state_from_device()

    async def async_will_remove_from_hass(self):
        """Unregister callbacks when entity is removed."""
        self._device.remove_callback(self._update_callback)

    def _update_callback(self):
        """Handle state update from the device."""
        self._update_state_from_device()
        self.async_write_ha_state()

    def _update_state_from_device(self):
        """Update state from device attributes."""
        # For toggle switches, sync the state
        if self._device.mode == "toggle":
            self._is_on = self._device.button_states.get(self._button_index, False)
            
        # For momentary switches, state is always off
        else:
            self._is_on = False

    @property
    def extra_state_attributes(self):
        """Return additional state attributes."""
        return {
            "device_id": self._device.device_id,
            "controller_id": self._device.controller.uid,
            "button_index": self._button_index,
            "mode": self._device.mode,
            "assigned_scene": self._device.get_assigned_scene(self._button_index)
        }