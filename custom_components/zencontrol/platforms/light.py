import logging
from homeassistant.components.light import LightEntity, ColorMode, ATTR_BRIGHTNESS, ATTR_RGB_COLOR

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    hub = hass.data["zencontrol"][config_entry.entry_id]
    entities = []
    
    for device_id, device in hub.devices.items():
        if isinstance(device, ZenLight):
            entities.append(ZenControlLightEntity(device))
    
    async_add_entities(entities)

class ZenControlLightEntity(LightEntity):
    def __init__(self, device):
        self._device = device
        self._attr_unique_id = device.device_id
        self._attr_name = device.device_id.replace("_", " ").title()
        
    @property
    def is_on(self):
        return self._device.state.get("state") == "on"
    
    @property
    def brightness(self):
        return self._device.state.get("brightness", 0)
    
    @property
    def rgb_color(self):
        return self._device.state.get("rgb_color", [255, 255, 255])
    
    @property
    def supported_color_modes(self):
        if "rgb_color" in self._device.state:
            return {ColorMode.RGB}
        return {ColorMode.BRIGHTNESS}
    
    async def async_turn_on(self, **kwargs):
        params = {}
        if ATTR_BRIGHTNESS in kwargs:
            params["brightness"] = kwargs[ATTR_BRIGHTNESS]
        if ATTR_RGB_COLOR in kwargs:
            params["rgb_color"] = kwargs[ATTR_RGB_COLOR]
        
        await self._device.turn_on(**params)
    
    async def async_turn_off(self, **kwargs):
        await self._device.turn_off()
    
    async def async_update(self):
        # Device state updated through multicast events
        pass