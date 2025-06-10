# config_flow.py
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

_LOGGER = logging.getLogger(__name__)

class ZenControlConfigFlow(config_entries.ConfigFlow, domain="zencontrol"):
    """Handle a config flow for ZenControl."""
    
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            return self.async_create_entry(
                title="ZenControl Hub", 
                data=user_input
            )
            
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Optional("multicast_group", default="239.255.90.67"): str,
                vol.Optional("multicast_port", default=5110): int,
                vol.Optional("udp_port", default=5108): int,
                vol.Optional("discovery_timeout", default=30): int,
            }),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ZenControlOptionsFlow(config_entry)

class ZenControlOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for ZenControl."""
    
    def __init__(self, config_entry):
        self.config_entry = config_entry
        
    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors = {}
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
            
        options = {
            vol.Optional(
                "discovery_timeout",
                default=self.config_entry.options.get("discovery_timeout", 30)
            ): int,
            vol.Optional(
                "command_timeout",
                default=self.config_entry.options.get("command_timeout", 2.0)
            ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=10.0)),
            vol.Optional(
                "controller_timeout",
                default=self.config_entry.options.get("controller_timeout", 60)
            ): int,
            vol.Optional(
                "enable_debug_logging",
                default=self.config_entry.options.get("enable_debug_logging", False)
            ): bool,
        }
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(options),
            errors=errors,
        )