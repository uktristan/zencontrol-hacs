import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, DEFAULT_MULTICAST_GROUP, DEFAULT_MULTICAST_PORT, DEFAULT_UDP_PORT

_LOGGER = logging.getLogger(__name__)

class ZenControlConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ZenControl."""
    
    VERSION = 2
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH
    
    def __init__(self):
        """Initialize the config flow."""
        self.controller_data = {}
        self.network_settings = {}
        
    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        return await self.async_step_network_settings()
    
    async def async_step_network_settings(self, user_input=None) -> FlowResult:
        """Configure network settings."""
        errors = {}
        
        if user_input is not None:
            # Validate inputs
            if not await self._validate_ports(user_input):
                errors["base"] = "invalid_ports"
            elif not await self._validate_multicast(user_input["multicast_group"]):
                errors["base"] = "invalid_multicast"
            else:
                self.network_settings = user_input
                return await self.async_step_controller_config()
        
        return self.async_show_form(
            step_id="network_settings",
            data_schema=vol.Schema({
                vol.Required(
                    "multicast_group",
                    default=self.network_settings.get("multicast_group", DEFAULT_MULTICAST_GROUP)
                ): str,
                vol.Required(
                    "multicast_port",
                    default=self.network_settings.get("multicast_port", DEFAULT_MULTICAST_PORT)
                ): cv.port,
                vol.Required(
                    "udp_port",
                    default=self.network_settings.get("udp_port", DEFAULT_UDP_PORT)
                ): cv.port,
            }),
            errors=errors,
            description_placeholders={
                "docs_url": "https://github.com/your-org/zencontrol-homeassistant"
            }
        )
    
    async def async_step_controller_config(self, user_input=None) -> FlowResult:
        """Add or configure ZenControllers."""
        errors = {}
        
        if user_input is not None:
            # Add new controller
            controller_id = user_input["controller_id"]
            ip_address = user_input["ip_address"]
            
            # Validate IP address
            if not await self._validate_ip(ip_address):
                errors["base"] = "invalid_ip"
            else:
                self.controller_data[controller_id] = {
                    "ip_address": ip_address,
                    "name": user_input.get("name", f"ZenController {controller_id}"),
                    "discovery_enabled": user_input.get("discovery_enabled", True)
                }
            
        # Prepare form
        controllers_list = [f"{cid} - {data['ip_address']}" for cid, data in self.controller_data.items()]
        
        data_schema = vol.Schema({
            vol.Required("controller_id"): str,
            vol.Required("ip_address"): str,
            vol.Optional("name"): str,
            vol.Optional("discovery_enabled", default=True): bool
        })
        
        return self.async_show_form(
            step_id="controller_config",
            data_schema=data_schema,
            errors=errors,
            description="Add ZenControllers to your network",
            last_step=False,
            # REMOVE THE DUPLICATE PARAMETERS BELOW:
            # step_id="controller_config",  # <-- DUPLICATE
            # data_schema=data_schema,      # <-- DUPLICATE
            # errors=errors,                # <-- DUPLICATE
            extra_action="add_another",
            extra_action_text="Add Another Controller"
        )
    
    async def async_step_add_another(self, user_input=None) -> FlowResult:
        """Handle 'Add Another' action."""
        return await self.async_step_controller_config(user_input)
    
    async def async_step_finish(self, user_input=None) -> FlowResult:
        """Finalize configuration."""
        # Create entry with all data
        config_data = {
            "network": self.network_settings,
            "controllers": self.controller_data
        }
        
        return self.async_create_entry(
            title="ZenControl Hub", 
            data=config_data
        )
    
    @staticmethod
    async def _validate_ports(user_input) -> bool:
        """Validate port configuration."""
        udp_port = user_input.get("udp_port")
        multicast_port = user_input.get("multicast_port")
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
    async def _validate_ip(address) -> bool:
        """Validate IP address format."""
        try:
            parts = [int(part) for part in address.split('.')]
            if len(parts) != 4:
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
        self.controller_options = dict(config_entry.data.get("controllers", {}))
        
    async def async_step_init(self, user_input=None) -> FlowResult:
        """Manage the main options."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["global_settings", "manage_controllers", "add_controller"]
        )
    
    async def async_step_global_settings(self, user_input=None) -> FlowResult:
        """Configure global settings."""
        errors = {}
        if user_input is not None:
            self.options.update(user_input)
            return self.async_create_entry(title="", data=self.options)
            
        defaults = {
            "command_timeout": self.options.get("command_timeout", 2.0),
            "controller_timeout": self.options.get("controller_timeout", 60),
            "enable_debug_logging": self.options.get("enable_debug_logging", False)
        }
        
        return self.async_show_form(
            step_id="global_settings",
            data_schema=vol.Schema({
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
            }),
            errors=errors,
        )
    
    async def async_step_manage_controllers(self, user_input=None) -> FlowResult:
        """Manage existing controllers."""
        if user_input is not None and "controller_id" in user_input:
            controller_id = user_input["controller_id"]
            if controller_id == "back":
                return await self.async_step_init()
                
            if controller_id in self.controller_options:
                return await self.async_step_edit_controller(
                    controller_id, 
                    self.controller_options[controller_id]
                )
        
        # List existing controllers
        controllers = [
            (cid, f"{data.get('name', cid)} ({data['ip_address']})")
            for cid, data in self.controller_options.items()
        ]
        controllers.append(("back", "Back to Main Menu"))
        
        return self.async_show_form(
            step_id="manage_controllers",
            data_schema=vol.Schema({
                vol.Required("controller_id"): vol.In(
                    {cid: label for cid, label in controllers}
                )
            })
        )
    
    async def async_step_edit_controller(self, controller_id, controller_data, user_input=None) -> FlowResult:
        """Edit an existing controller."""
        errors = {}
        
        if user_input is not None:
            # Update controller data
            if "remove" in user_input and user_input["remove"]:
                del self.controller_options[controller_id]
                # Save updated controller list to config entry
                new_data = {**self.config_entry.data}
                new_data["controllers"] = self.controller_options
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=new_data
                )
                return await self.async_step_manage_controllers()
                
            # Update controller settings
            if not await ZenControlConfigFlow._validate_ip(user_input["ip_address"]):
                errors["base"] = "invalid_ip"
            else:
                self.controller_options[controller_id] = {
                    "ip_address": user_input["ip_address"],
                    "name": user_input.get("name", controller_id),
                    "discovery_enabled": user_input.get("discovery_enabled", True)
                }
                # Save updated controller list to config entry
                new_data = {**self.config_entry.data}
                new_data["controllers"] = self.controller_options
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=new_data
                )
                return await self.async_step_manage_controllers()
        
        return self.async_show_form(
            step_id="edit_controller",
            data_schema=vol.Schema({
                vol.Required("ip_address", default=controller_data["ip_address"]): str,
                vol.Optional("name", default=controller_data.get("name", controller_id)): str,
                vol.Optional("discovery_enabled", default=controller_data.get("discovery_enabled", True)): bool,
                vol.Optional("remove", default=False): bool
            }),
            errors=errors,
            description=f"Editing controller: {controller_id}",
            # REMOVE THE DUPLICATE PARAMETERS BELOW:
            # step_id="edit_controller",  # <-- DUPLICATE
            last_step=False
        )
    
    async def async_step_add_controller(self, user_input=None) -> FlowResult:
        """Add a new controller."""
        errors = {}
        
        if user_input is not None:
            controller_id = user_input["controller_id"]
            ip_address = user_input["ip_address"]
            
            # Validate IP address
            if not await ZenControlConfigFlow._validate_ip(ip_address):
                errors["base"] = "invalid_ip"
            elif controller_id in self.controller_options:
                errors["base"] = "duplicate_id"
            else:
                # Add new controller
                self.controller_options[controller_id] = {
                    "ip_address": ip_address,
                    "name": user_input.get("name", f"ZenController {controller_id}"),
                    "discovery_enabled": user_input.get("discovery_enabled", True)
                }
                # Save updated controller list to config entry
                new_data = {**self.config_entry.data}
                new_data["controllers"] = self.controller_options
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=new_data
                )
                return await self.async_step_manage_controllers()
        
        return self.async_show_form(
            step_id="add_controller",
            data_schema=vol.Schema({
                vol.Required("controller_id"): str,
                vol.Required("ip_address"): str,
                vol.Optional("name"): str,
                vol.Optional("discovery_enabled", default=True): bool
            }),
            errors=errors,
            description="Add a new ZenController"
        )