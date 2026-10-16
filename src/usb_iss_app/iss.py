"""Layer 2: USB-ISS protocol. Pure builders/parsers plus thin helpers."""
from __future__ import annotations

from typing import NamedTuple

from .transport import Transport

ISS_CMD = 0x5A  # datasheet p.5
MODULE_ID = 7


class IssError(Exception):
    pass


class IssTimeout(IssError):
    """Fewer bytes than expected were received."""


class IssProtocolError(IssError):
    """Response bytes violate the datasheet."""


class Version(NamedTuple):
    module_id: int
    firmware: int
    mode: int  # raw ISS_MODE byte; decoded in iteration 01


# ISS_VERSION (0x01), datasheet p.5: send 5A 01, receive module_id(7) firmware mode.
def build_version() -> bytes:
    return bytes([ISS_CMD, 0x01])


def parse_version(resp: bytes) -> Version:
    if len(resp) < 3:
        raise IssTimeout(f"ISS_VERSION: expected 3 bytes, got {len(resp)}")
    if resp[0] != MODULE_ID:
        raise IssProtocolError(f"ISS_VERSION: module_id {resp[0]} != {MODULE_ID}")
    return Version(resp[0], resp[1], resp[2])


# GET_SER_NUM (0x03), datasheet p.5: send 5A 03, receive 8 ASCII digits 0x30-0x39.
def build_serial_number() -> bytes:
    return bytes([ISS_CMD, 0x03])


def parse_serial_number(resp: bytes) -> str:
    if len(resp) < 8:
        raise IssTimeout(f"GET_SER_NUM: expected 8 bytes, got {len(resp)}")
    resp = resp[:8]
    if any(not 0x30 <= b <= 0x39 for b in resp):
        raise IssProtocolError(f"GET_SER_NUM: non-digit byte in {resp.hex(' ')}")
    return resp.decode("ascii")


def version(transport: Transport) -> Version:
    transport.write(build_version())
    return parse_version(transport.read(3))


def serial_number(transport: Transport) -> str:
    transport.write(build_serial_number())
    return parse_serial_number(transport.read(8))
