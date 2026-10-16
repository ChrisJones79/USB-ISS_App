"""Layer 1: raw byte transport (SPEC §3)."""
from __future__ import annotations

import abc
import os
from pathlib import Path

DEFAULT_TIMEOUT = 0.5  # datasheet p.11: 500 ms


class Transport(abc.ABC):
    @abc.abstractmethod
    def write(self, data: bytes) -> None: ...

    @abc.abstractmethod
    def read(self, n: int, timeout: float = DEFAULT_TIMEOUT) -> bytes:
        """Read up to n bytes; returns fewer on timeout."""

    @abc.abstractmethod
    def close(self) -> None: ...


def parse_env_file(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE parser (comments with #, optional quotes)."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def find_port(env_file: Path | None = None) -> str | None:
    """USB_ISS_PORT from the environment, else from .env (repo root)."""
    if os.environ.get("USB_ISS_PORT"):
        return os.environ["USB_ISS_PORT"]
    if env_file is None:
        env_file = Path(__file__).resolve().parents[2] / ".env"
    return parse_env_file(env_file).get("USB_ISS_PORT") or None


class SerialTransport(Transport):
    def __init__(self, port: str | None = None, timeout: float = DEFAULT_TIMEOUT):
        import serial  # pyserial

        port = port or find_port()
        if not port:
            raise ValueError("USB_ISS_PORT is not set (environment or .env)")
        # Baud has no effect on the USB-ISS (datasheet p.4); pyserial default is used.
        self._ser = serial.Serial(port, timeout=timeout)
        self._ser.reset_input_buffer()

    def write(self, data: bytes) -> None:
        self._ser.write(data)
        self._ser.flush()

    def read(self, n: int, timeout: float = DEFAULT_TIMEOUT) -> bytes:
        self._ser.timeout = timeout
        return self._ser.read(n)

    def close(self) -> None:
        self._ser.close()
