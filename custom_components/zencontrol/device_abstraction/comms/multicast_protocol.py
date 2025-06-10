import asyncio
import logging
import socket
import json

_LOGGER = logging.getLogger(__name__)

class ZenMulticastProtocol:
    """Handles multicast communication for real-time events."""
    
    def __init__(self, group: str, port: int):
        self.group = group
        self.port = port
        self.listeners: List[Callable[[dict], None]] = []
        self.transport = None
        
    async def start(self):
        """Join multicast group and start listening."""
        loop = asyncio.get_running_loop()
        
        # Create UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', self.port))
        
        # Join multicast group
        group_bin = socket.inet_aton(self.group)
        mreq = group_bin + socket.inet_aton('0.0.0.0')
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        
        # Create protocol
        self.transport, _ = await loop.create_datagram_endpoint(
            lambda: MulticastProtocol(self.handle_datagram),
            sock=sock
        )
        _LOGGER.info("Joined multicast group %s:%d", self.group, self.port)
        
    async def stop(self):
        """Leave multicast group and stop listening."""
        if self.transport:
            self.transport.close()
            self.transport = None
            _LOGGER.debug("Multicast listener stopped")
            
    def add_listener(self, callback: Callable[[dict], None]):
        """Add an event listener."""
        self.listeners.append(callback)
        
    def remove_listener(self, callback: Callable[[dict], None]):
        """Remove an event listener."""
        if callback in self.listeners:
            self.listeners.remove(callback)
            
    def handle_datagram(self, data: bytes, addr: tuple):
        """Handle incoming multicast datagram."""
        try:
            event = json.loads(data.decode())
            _LOGGER.debug("Received multicast event from %s: %s", addr, event)
            
            for callback in self.listeners:
                try:
                    callback(event)
                except Exception as e:
                    _LOGGER.exception("Error in multicast listener: %s", e)
        except json.JSONDecodeError:
            _LOGGER.warning("Received malformed multicast data from %s", addr)
        except UnicodeDecodeError:
            _LOGGER.warning("Received non-UTF8 multicast data from %s", addr)

class MulticastProtocol:
    """Asyncio protocol for multicast communication."""
    def __init__(self, data_handler):
        self.data_handler = data_handler
        self.transport = None
        
    def connection_made(self, transport):
        self.transport = transport
        
    def datagram_received(self, data, addr):
        self.data_handler(data, addr)
        
    def error_received(self, exc):
        _LOGGER.error("Multicast error: %s", exc)
        
    def connection_lost(self, exc):
        _LOGGER.debug("Multicast connection closed")