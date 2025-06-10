import logging
from homeassistant.components.binary_sensor import BinarySensorEntity

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    hub = hass.data["zencontrol"][config_entry.entry_id]
    entities = []
    
    for device_id, device in hub.devices.items():
        if isinstance(device, ZenSensor):
            entities.append(ZenControlMotionEntity(device))
    
    async_add_entities(entities)

class ZenControlMotionEntity(BinarySensorEntity):
    def __init__(self, device):
        self._device = device
        self._attr_unique_id = f"{device.device_id}_motion"
        self._attr_name = f"{device.device_id.replace('_', ' ').title()} Motion"
        self._attr_device_class = "motion"
    
    @property
    def is_on(self):
        return self._device.state.get("motion_active", False)
    
    async def async_update(self):
        # State updated through multicast events
        pass