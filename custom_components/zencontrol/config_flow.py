import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN, DEFAULT_MULTICAST_GROUP, DEFAULT_MULTICAST_PORT, DEFAULT_UDP_PORT, DEFAULT_DISCOVERY_TIMEOUT

_LOGGER = logging.getLogger(__name__)

class ZenControlConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ZenControl."""
    
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH
    
    def __init__(self):
        """Initialize the config flow."""
        self._user_input = {}
        
    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        
        if user_input is not None:
            self._user_input = user_input
            # Validate inputs
            if not await self._validate_ports(user_input):
                errors["base"] = "invalid_ports"
            elif not await self._validate_multicast(user_input["multicast_group"]):
                errors["base"] = "invalid_multicast"
            else:
                # Create entry
                return self.async_create_entry(
                    title="ZenControl Hub", 
                    data=user_input
                )
        
        # Use stored input or defaults for form values
        defaults = self._user_input or {
            "multicast_group": DEFAULT_MULTICAST_GROUP,
            "multicast_port": DEFAULT_MULTICAST_PORT,
            "udp_port": DEFAULT_UDP_PORT,
            "discovery_timeout": DEFAULT_DISCOVERY_TIMEOUT
        }
        
        # Show form with current values
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(
                    "multicast_group",
                    default=defaults["multicast_group"]
                ): str,
                vol.Required(
                    "multicast_port",
                    default=defaults["multicast_port"]
                ): cv.port,
                vol.Required(
                    "udp_port",
                    default=defaults["udp_port"]
                ): cv.port,
                vol.Optional(
                    "discovery_timeout",
                    default=defaults.get("discovery_timeout", DEFAULT_DISCOVERY_TIMEOUT)
                ): vol.All(cv.positive_int, vol.Range(min=5, max=300)),
            }),
            errors=errors,
            description_placeholders={
                "docs_url": "https://github.com/your-org/zencontrol-homeassistant"
            }
        )
    
    async def async_step_import(self, import_config):
        """Handle import from YAML configuration."""
        # Store imported config and show form to confirm
        self._user_input = import_config
        return await self.async_step_user()
    
    @staticmethod
    async def _validate_ports(user_input) -> bool:
        """Validate port configuration."""
        udp_port = user_input.get("udp_port")
        multicast_port = user_input.get("multicast_port")
        
        # Ports must be different
        return udp_port != multicast_port
    
    @staticmethod
    async def _validate_multicast(address) -> bool:
        """Validate multicast address format."""
        try:
            parts = [int(part) for part in address.split('.')]
            if len(parts) != 4:
                return False
            if not (224 <= parts[0] <= 239):
                return False
            return all(0 <= part <= 255 for part in parts)
        except ValueError:
            return False
    
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ZenControlOptionsFlow(config_entry)

class ZenControlOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for ZenControl."""
    
    def __init__(self, config_entry):
        self.config_entry = config_entry
        self.options = dict(config_entry.options)
        
    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors = {}
        if user_input is not None:
            # Validate discovery timeout
            if 5 <= user_input.get("discovery_timeout", 30) <= 300:
                self.options.update(user_input)
                return self.async_create_entry(title="", data=self.options)
            errors["base"] = "invalid_timeout"
            
        # Set defaults from options or config entry
        defaults = {
            "discovery_timeout": self.options.get("discovery_timeout", 30),
            "command_timeout": self.options.get("command_timeout", 2.0),
            "controller_timeout": self.options.get("controller_timeout", 60),
            "enable_debug_logging": self.options.get("enable_debug_logging", False)
        }
        
        options_schema = vol.Schema({
            vol.Required(
                "discovery_timeout",
                default=defaults["discovery_timeout"]
            ): vol.All(cv.positive_int, vol.Range(min=5, max=300)),
            vol.Required(
                "command_timeout",
                default=defaults["command_timeout"]
            ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=10.0)),
            vol.Required(
                "controller_timeout",
                default=defaults["controller_timeout"]
            ): vol.All(cv.positive_int, vol.Range(min=30, max=600)),
            vol.Optional(
                "enable_debug_logging",
                default=defaults["enable_debug_logging"]
            ): bool,
        })
        
        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            errors=errors,
        )