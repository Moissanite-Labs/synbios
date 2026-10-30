"""Packet-layer rejections (fail closed before forge commands)."""


class PacketRejected(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status
