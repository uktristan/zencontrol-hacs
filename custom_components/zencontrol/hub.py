import asyncio
import logging
import json
from typing import Dict, Optional, Callable, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .device_abstraction.comms.udp_protocol import ZenUDPProtocol
from .device_abstraction.comms.multicast_protocol import ZenMulticastProtocol
from .device_abstraction.controller import ZenControllerRegistry, ZenController
from .device_abstraction.devices import ZenDevice, ZenLight, ZenSwitch, ZenSensor
from .discovery_manager import DISCOVERY_SIGNAL

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class ZenControlHub:
    """Hub for ZenControl integration."""
    
    def __init__(
        self,
        hass: HomeAssistant,
        multicast_group: str,
        multicast_port: int,
        udp_port: int,
        discovery_timeout: int
    ):
        self.hass = hass
        self.multicast_group = multicast_group
        self.multicast_port = multicast_port
        self.udp_port = udp_port
        self.discovery_timeout = discovery_timeout
        
        # Communication protocols
        self.udp = ZenUDPProtocol(self.udp_port)
        self.multicast = ZenMulticastProtocol(self.multicast_group, self.multicast_port)
        
        # Device management
        self.registry = ZenControllerRegistry()
        self.devices: Dict[str, ZenDevice] = {}
        self.discovery_manager = None
        
        # Register multicast listeners
        self.multicast.add_listener(self.handle_multicast_event)
        
    async def start(self):
        """Start communication layers."""
        await self.udp.start()
        await self.multicast.start()
        _LOGGER.info("Communication protocols started")
        
    async def stop(self):
        """Stop communication layers and clean up."""
        if self.udp:
            await self.udp.stop()
        if self.multicast:
            await self.multicast.stop()
        _LOGGER.info("Communication protocols stopped")
        
    def get_device(self, device_id: str) -> Optional[ZenDevice]:
        """Get a device by ID."""
        return self.devices.get(device_id)
        
    def add_device(self, device: ZenDevice):
        """Add a device to the hub."""
        self.devices[device.device_id] = device
        device.register_hass(self.hass)
        _LOGGER.debug("Added device: %s", device.device_id)
        
    def remove_device(self, device_id: str):
        """Remove a device from the hub."""
        if device_id in self.devices:
            del self.devices[device_id]
            _LOGGER.debug("Removed device: %s", device_id)
            
    def handle_multicast_event(self, event: dict):
        """Process incoming multicast events."""
        if not event:
            return
            
        event_type = event.get("type")
        
        if event_type == "controller_status":
            self._handle_controller_event(event)
        elif event_type == "device_event":
            self._handle_device_event(event)
        else:
            _LOGGER.debug("Received unknown event type: %s", event_type)
            
    def _handle_controller_event(self, event: dict):
        """Process controller status event."""
        uid = event.get("controller_id")
        ip = event.get("ip_address")
        
        if not uid or not ip:
            _LOGGER.warning("Invalid controller event: %s", event)
            return
            
        controller = self.registry.add_controller(uid, ip)
        controller.update_heartbeat()
        
        status = event.get("status")
        if status == "startup_complete":
            controller.mark_ready()
            _LOGGER.info("Controller %s (%s) is ready", uid, ip)
        elif status == "shutdown":
            controller.is_ready = False
            _LOGGER.warning("Controller %s (%s) is shutting down", uid, ip)
        else:
            _LOGGER.debug("Controller %s status: %s", uid, status)
    
    def _handle_device_event(self, event: dict):
        """Process device event."""
        device_id = event.get("device_id")
        if not device_id:
            _LOGGER.warning("Device event missing device_id: %s", event)
            return
            
        if device := self.devices.get(device_id):
            event_subtype = event.get("subtype")
            
            if event_subtype == "button":
                button = event.get("button")
                action = event.get("action")
                if button is None or not action:
                    _LOGGER.warning("Invalid button event: %s", event)
                else:
                    device.handle_button_event(button, action)
            elif event_subtype == "motion":
                active = event.get("active")
                if active is None:
                    _LOGGER.warning("Invalid motion event: %s", event)
                else:
                    device.handle_motion(active)
            elif event_subtype == "occupancy":
                active = event.get("active")
                if active is None:
                    _LOGGER.warning("Invalid occupancy event: %s", event)
                else:
                    device.handle_occupancy(active)
            elif event_subtype == "light_state":
                state = event.get("state")
                if state is None:
                    _LOGGER.warning("Invalid light_state event: %s", event)
                else:
                    device.update_state(state)
            else:
                _LOGGER.warning("Unknown device event subtype: %s", event_subtype)
        else:
            _LOGGER.debug("Event for unknown device: %s", device_id)
            
    @callback
    def handle_discovery_event(self, event_data: dict):
        """Handle discovery events from discovery manager."""
        action = event_data.get("action")
        device_id = event_data.get("device_id")
        
        if action == "add" and device_id:
            if device := self.devices.get(device_id):
                # Notify platforms about new device
                async_dispatcher_send(
                    self.hass,
                    f"{DOMAIN}_device_added",
                    device_id
                )
        elif event_data.get("status") == "complete":
            _LOGGER.info("Device discovery completed with %d devices", len(self.devices))
            
    async def controller_watchdog(self):
        """Periodically check controller health."""
        _LOGGER.info("Starting controller watchdog")
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                self.registry.remove_stale_controllers(120)  # 2 minute timeout
                
                # Log controller status
                for controller in self.registry.controllers.values():
                    status = "ready" if controller.is_ready else "offline"
                    last_seen_min = (asyncio.get_event_loop().time() - controller.last_seen) / 60
                    _LOGGER.debug(
                        "Controller %s (%s): %s, last seen: %.1f min ago",
                        controller.uid,
                        controller.ip,
                        status,
                        last_seen_min
                    )
                    
            except asyncio.CancelledError:
                _LOGGER.info("Controller watchdog cancelled")
                break
            except Exception as e:
                _LOGGER.exception("Error in controller watchdog: %s", e)
                await asyncio.sleep(60)