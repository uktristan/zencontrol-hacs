import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

_LOGGER = logging.getLogger(__name__)

@config_entries.HANDLERS.register(DOMAIN)
class ZenControlConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ZenControl."""
    
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH
    
    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        errors = {}
        
        if user_input is not None:
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
        
        # Show form with current values or defaults
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(
                    "multicast_group",
                    default=self._get_default("multicast_group", "239.255.90.67")
                ): str,
                vol.Required(
                    "multicast_port",
                    default=self._get_default("multicast_port", 5110)
                ): vol.All(vol.Coerce(int), vol.Range(min=1024, max=65535)),
                vol.Required(
                    "udp_port",
                    default=self._get_default("udp_port", 5108)
                ): vol.All(vol.Coerce(int), vol.Range(min=1024, max=65535)),
                vol.Optional(
                    "discovery_timeout",
                    default=self._get_default("discovery_timeout", 30)
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
            }),
            errors=errors,
            description_placeholders={
                "docs_url": "https://github.com/your-org/zencontrol-homeassistant"
            }
        )
    
    async def async_step_import(self, import_config) -> FlowResult:
        """Handle import from YAML configuration."""
        # Migrate YAML config to config entry
        return await self.async_step_user(import_config)
    
    @staticmethod
    def _get_default(key, default_value):
        """Get default value maintaining existing settings."""
        return lambda _: default_value
    
    @staticmethod
    async def _validate_ports(user_input) -> bool:
        """Validate port configuration."""
        udp_port = user_input.get("udp_port")
        multicast_port = user_input.get("multicast_port")
        
        # Ports must be different
        if udp_port == multicast_port:
            return False
            
        # Ports must be in valid range (handled by schema)
        return True
    
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
        
    async def async_step_init(self, user_input=None) -> FlowResult:
        """Manage the options."""
        errors = {}
        if user_input is not None:
            # Validate discovery timeout
            if 5 <= user_input.get("discovery_timeout", 30) <= 300:
                self.options.update(user_input)
                return self.async_create_entry(title="", data=self.options)
            errors["base"] = "invalid_timeout"
            
        options_schema = vol.Schema({
            vol.Required(
                "discovery_timeout",
                default=self.options.get("discovery_timeout", 30)
            ): int,
            vol.Required(
                "command_timeout",
                default=self.options.get("command_timeout", 2.0)
            ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=10.0)),
            vol.Required(
                "controller_timeout",
                default=self.options.get("controller_timeout", 60)
            ): vol.All(vol.Coerce(int), vol.Range(min=30, max=600)),
            vol.Optional(
                "enable_debug_logging",
                default=self.options.get("enable_debug_logging", False)
            ): bool,
        })
        
        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            errors=errors,
        )