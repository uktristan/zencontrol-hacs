import asyncio
import logging
import socket

_LOGGER = logging.getLogger(__name__)

class ZenUDPProtocol:
    """Handles UDP communication with ZenControl controllers."""
    
    def __init__(self, port: int):
        self.port = port
        self.sequence_counter = 0
        self.pending_commands: Dict[int, asyncio.Future] = {}
        self.transport = None
        
    async def start(self):
        """Start UDP listener."""
        loop = asyncio.get_running_loop()
        self.transport, _ = await loop.create_datagram_endpoint(
            lambda: UDPProtocol(self.handle_datagram),
            local_addr=('0.0.0.0', self.port)
        )
        _LOGGER.info("UDP server started on port %d", self.port)
        
    async def stop(self):
        """Stop UDP listener."""
        if self.transport:
            self.transport.close()
            self.transport = None
            _LOGGER.debug("UDP server stopped")
            
    async def send_command(
        self, 
        controller_ip: str,
        command: bytes,
        timeout: float = 2.0
    ) -> bytes:
        """Send command with sequence tracking."""
        seq = self._next_sequence()
        full_command = seq.to_bytes(2, 'big') + command
        future = asyncio.get_running_loop().create_future()
        self.pending_commands[seq] = future
        
        try:
            self.transport.sendto(full_command, (controller_ip, self.port))
            _LOGGER.debug("Sent to %s: [Seq %d] %s", controller_ip, seq, command.hex())
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            _LOGGER.warning("Command timeout to %s: [Seq %d]", controller_ip, seq)
            raise
        finally:
            self.pending_commands.pop(seq, None)
            
    def handle_datagram(self, data: bytes, addr: tuple):
        """Handle incoming UDP datagram."""
        if len(data) < 2:
            _LOGGER.warning("Received malformed UDP packet from %s", addr)
            return
            
        seq = int.from_bytes(data[:2], 'big')
        payload = data[2:]
        
        if future := self.pending_commands.get(seq):
            future.set_result(payload)
            _LOGGER.debug("Received response for seq %d from %s", seq, addr)
        else:
            _LOGGER.warning("Received unexpected response for seq %d from %s", seq, addr)
            
    def _next_sequence(self) -> int:
        self.sequence_counter = (self.sequence_counter + 1) % 65536
        return self.sequence_counter

class UDPProtocol:
    """Asyncio protocol for UDP communication."""
    def __init__(self, data_handler):
        self.data_handler = data_handler
        self.transport = None
        
    def connection_made(self, transport):
        self.transport = transport
        
    def datagram_received(self, data, addr):
        self.data_handler(data, addr)
        
    def error_received(self, exc):
        _LOGGER.error("UDP error: %s", exc)
        
    def connection_lost(self, exc):
        _LOGGER.debug("UDP connection closed")