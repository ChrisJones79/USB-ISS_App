import pytest

from usb_iss_app import iss
from usb_iss_app.mock import MockTransport


class Scripted:
    """Transport returning canned bytes and recording writes."""

    def __init__(self, resp: bytes):
        self.resp, self.sent = resp, b""

    def write(self, data):
        self.sent += data

    def read(self, n, timeout=0.5):
        return self.resp[:n]


def test_version_mock_defaults(mock):
    assert iss.version(mock) == (7, 0x09, 0x40)


def test_version_request_bytes():
    t = Scripted(bytes([7, 2, 0x40]))
    assert iss.version(t) == (7, 2, 0x40)
    assert t.sent == bytes.fromhex("5A 01")


def test_version_configurable():
    assert iss.version(MockTransport(firmware=3, mode=0x62)) == (7, 3, 0x62)


def test_version_short_response():
    t = Scripted(bytes([7, 2]))
    with pytest.raises(iss.IssTimeout):
        iss.version(t)
    assert t.sent == bytes.fromhex("5A 01")


def test_version_bad_module_id():
    with pytest.raises(iss.IssProtocolError):
        iss.version(Scripted(bytes([8, 2, 0x40])))


def test_serial_mock_default(mock):
    assert iss.serial_number(mock) == "00000001"


def test_serial_request_bytes():
    t = Scripted(b"12345678")
    assert iss.serial_number(t) == "12345678"
    assert t.sent == bytes.fromhex("5A 03")


def test_serial_short_response():
    t = Scripted(b"1234567")
    with pytest.raises(iss.IssTimeout):
        iss.serial_number(t)
    assert t.sent == bytes.fromhex("5A 03")


@pytest.mark.parametrize("bad", [b"1234567A", b"1234567/", b"1234567:", b"\x001234567"])
def test_serial_non_digit(bad):
    with pytest.raises(iss.IssProtocolError):
        iss.serial_number(Scripted(bad))


def test_mock_unhandled_returns_nothing(mock):
    mock.write(bytes.fromhex("5A 02 40 00"))  # ISS_MODE not implemented
    assert mock.read(8) == b""
    assert mock.unhandled


def test_mock_unhandled_then_valid(mock):
    mock.write(bytes.fromhex("5A 7F"))
    assert mock.read(3) == b""
    assert iss.version(mock).module_id == 7


def test_mock_close(mock):
    mock.close()
    assert mock.closed
