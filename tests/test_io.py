"""Iteration 02: SERIAL_IO, SETPINS, GETPINS, GETAD (datasheet pp.19-20) and the mock's I/O state."""
import pytest

from usb_iss_app import iss
from usb_iss_app.mock import MockTransport

B = bytes.fromhex


def test_constants():
    assert (iss.SERIAL_IO, iss.SETPINS, iss.GETPINS, iss.GETAD) == (0x62, 0x63, 0x64, 0x65)
    assert (iss.SERIAL_TX_MAX, iss.SERIAL_RX_MAX) == (30, 62)


# ---- SERIAL_IO builders and parsers ----
def test_serial_io_frames():
    assert iss.build_serial_io() == B("62")
    assert iss.build_serial_io(bytes(range(30))) == b"\x62" + bytes(range(30))


def test_serial_io_31_refused():
    with pytest.raises(ValueError):
        iss.build_serial_io(bytes(31))


def test_serial_header():
    assert iss.parse_serial_io_header(B("FF 00 00")) == (True, 0, 0)
    assert iss.parse_serial_io_header(B("00 1E 3E")) == (False, 30, 62)


@pytest.mark.parametrize("resp,exc", [
    (B(""), iss.IssTimeout), (B("FF 00"), iss.IssTimeout),
    (B("01 00 00"), iss.IssProtocolError), (B("FE 00 00"), iss.IssProtocolError),
    (B("FF 1F 00"), iss.IssProtocolError), (B("FF 00 3F"), iss.IssProtocolError),
])
def test_serial_header_errors(resp, exc):
    with pytest.raises(exc):
        iss.parse_serial_io_header(resp)


class Scripted(MockTransport):
    """Replies to one SERIAL_IO with canned bytes."""

    def __init__(self, reply):
        super().__init__()
        self.reply = reply

    def write(self, data):
        self.sent = data
        self._rx += self.reply


@pytest.mark.parametrize("n", [0, 62])
def test_serial_io_ack_with_rx(n):
    t = Scripted(bytes([0xFF, 0, n]) + bytes(range(n)))
    assert iss.serial_io(t) == iss.SerialIoResult(True, 0, bytes(range(n)))


def test_serial_io_nack_still_returns_rx():
    t = Scripted(B("00 14 03 AA BB CC"))
    assert iss.serial_io(t, b"x") == iss.SerialIoResult(False, 20, B("AA BB CC"))


def test_serial_io_short_rx_body():
    with pytest.raises(iss.IssTimeout):
        iss.serial_io(Scripted(B("FF 00 04 01 02")))


# ---- SETPINS / GETPINS / GETAD builders and parsers ----
def test_pin_frames():
    assert iss.build_set_pins(0x0F) == B("63 0F")
    assert iss.build_set_pins(0) == B("63 00")
    assert iss.build_get_pins() == B("64")
    assert [iss.build_get_ad(c) for c in (1, 4)] == [B("65 01"), B("65 04")]


@pytest.mark.parametrize("v", [-1, 0x10, 0xFF])
def test_set_pins_range(v):
    with pytest.raises(ValueError):
        iss.build_set_pins(v)


@pytest.mark.parametrize("c", [0, 5, -1])
def test_get_ad_channel_range(c):
    with pytest.raises(ValueError):
        iss.build_get_ad(c)


def test_parse_set_pins():
    iss.parse_set_pins(B("FF"))
    with pytest.raises(iss.IssNack) as e:
        iss.parse_set_pins(B("00"))
    assert e.value.reason is None and "SETPINS" in str(e.value)
    with pytest.raises(iss.IssProtocolError):
        iss.parse_set_pins(B("01"))
    with pytest.raises(iss.IssTimeout):
        iss.parse_set_pins(B(""))


def test_iss_nack_mode_behaviour_unchanged():
    e = iss.IssNack(0x05)
    assert e.reason == 5 and e.name == "Unknown command" and "ISS_MODE" in str(e)


def test_parse_get_pins():
    assert iss.parse_get_pins(B("F5")) == 0x05
    assert iss.parse_get_pins(B("0A")) == 0x0A
    with pytest.raises(iss.IssTimeout):
        iss.parse_get_pins(B(""))


@pytest.mark.parametrize("resp,v", [("02 A6", 678), ("00 3D", 61), ("03 FF", 1023), ("00 00", 0)])
def test_parse_get_ad(resp, v):
    assert iss.parse_get_ad(B(resp)) == v


def test_parse_get_ad_errors():
    with pytest.raises(iss.IssProtocolError):
        iss.parse_get_ad(B("04 00"))
    for r in ("", "02"):
        with pytest.raises(iss.IssTimeout):
            iss.parse_get_ad(B(r))


# ---- mock: pin state ----
def io_mock(io_type, mode=iss.IO_MODE):
    m = MockTransport(mode=0x40)
    iss.set_mode(m, iss.build_i2c_mode(iss.I2C_S_100KHZ, 0xAA))
    if mode == iss.IO_MODE:
        iss.set_mode(m, iss.build_io_mode(io_type))
    return m


def test_mock_power_up_all_inputs():
    m = MockTransport()
    assert m.io_type == 0xAA
    m.inputs = 0b1111
    assert iss.get_pins(m) == 0b0011  # default mode is I2C: only pins 1 and 2 are general I/O

def test_mock_inputs_follow_levels():
    m = io_mock(0xAA)
    m.inputs = 0b0101
    assert iss.get_pins(m) == 0b0101
    m.inputs = 0b1111
    assert iss.get_pins(m) == 0b1111


def test_mock_outputs_and_setpins():
    # I/O1 output high, I/O2 output low, I/O3 input, I/O4 input
    m = io_mock(iss.io_type(1, 0, 2, 2))
    m.inputs = 0b1100
    assert iss.get_pins(m) == 0b1101
    iss.set_pins(m, 0b1110)  # only output pins change
    assert iss.get_pins(m) == 0b1110
    iss.set_pins(m, 0)
    assert iss.get_pins(m) == 0b1100


def test_mock_io_type_reapplied_resets_outputs():
    m = io_mock(iss.io_type(0, 0, 2, 2))
    iss.set_pins(m, 0b0011)
    assert iss.get_pins(m) & 3 == 3
    iss.set_mode(m, iss.build_io_change(iss.io_type(0, 0, 2, 2)))
    assert iss.get_pins(m) & 3 == 0


def test_mock_setpins_nack_hook():
    m = io_mock(0xAA)
    m.force_next_setpins_nack()
    with pytest.raises(iss.IssNack):
        iss.set_pins(m, 1)
    iss.set_pins(m, 1)  # one-shot


def test_mock_setpins_no_outputs_acks():
    m = io_mock(0xAA)
    iss.set_pins(m, 0x0F)
    assert iss.get_pins(m) == 0


def test_mock_getad():
    m = io_mock(0xFF)
    m.adc = [678, 61, 1023, 0]
    assert [iss.get_ad(m, c) for c in (1, 2, 3, 4)] == [678, 61, 1023, 0]
    m.write(B("65 00"))
    assert m.read(2) == B("00 00")
    m.write(B("65 05"))
    assert m.read(2) == B("00 00")


def test_mock_getad_digital_pin_is_zero():
    m = io_mock(iss.io_type(2, 2, 3, 3))
    m.adc = [500, 500, 500, 500]
    assert [iss.get_ad(m, c) for c in (1, 2, 3, 4)] == [0, 0, 500, 500]


def test_mock_general_pins_by_mode():
    # I2C: pins 1,2 only. IO_TYPE bits for pins 3,4 are ignored.
    m = MockTransport(mode=0x40)
    iss.set_mode(m, iss.build_i2c_mode(iss.I2C_S_100KHZ, iss.io_type(2, 2, 1, 1)))
    m.inputs = 0b1111
    assert iss.get_pins(m) == 0b0011
    # SPI: none
    iss.set_mode(m, iss.build_spi_mode(0, 1_000_000))
    assert iss.get_pins(m) == 0
    # IO_MODE+SERIAL: pins 3,4 only
    iss.set_mode(m, iss.build_io_serial(9600, iss.io_type(2, 2, 2, 2)))
    assert iss.get_pins(m) == 0b1100
    # I2C+SERIAL: none
    iss.set_mode(m, iss.build_i2c_serial(iss.I2C_S_100KHZ, 9600))
    assert iss.get_pins(m) == 0


def test_mock_spi_and_i2c_serial_keep_io_type():
    m = io_mock(iss.io_type(2, 2, 1, 1))
    iss.set_mode(m, iss.build_spi_mode(0, 1_000_000))
    assert m.io_type == iss.io_type(2, 2, 1, 1)
    iss.set_mode(m, iss.build_i2c_serial(iss.I2C_S_100KHZ, 9600))
    assert m.io_type == iss.io_type(2, 2, 1, 1)


# ---- mock: SERIAL_IO ----
def serial_mock():
    m = MockTransport(mode=0x40)
    iss.set_mode(m, iss.build_io_serial(115200, 0xAA))
    return m


def test_mock_serial_poll_empty():
    assert iss.serial_io(serial_mock()) == (True, 0, b"")


def test_mock_serial_send_30():
    m = serial_mock()
    data = bytes(range(30))
    assert iss.serial_io(m, data).ack
    assert bytes(m.serial_sent) == data


def test_mock_serial_nack_when_full():
    m = serial_mock()
    m.hold_serial_tx = True
    assert iss.serial_io(m, bytes(20)) == (True, 20, b"")
    r = iss.serial_io(m, bytes(11))
    assert (r.ack, r.tx_count) == (False, 20)
    assert bytes(m.serial_sent) == b""
    m.hold_serial_tx = False
    assert iss.serial_io(m).tx_count == 0
    assert bytes(m.serial_sent) == bytes(20)


def test_mock_serial_rx_cap():
    m = serial_mock()
    m.inject_serial_rx(bytes(range(70)))
    r = iss.serial_io(m)
    assert r.rx == bytes(range(62))
    assert iss.serial_io(m).rx == b""


def test_mock_serial_nack_carries_rx():
    m = serial_mock()
    m.hold_serial_tx = True
    iss.serial_io(m, bytes(30))
    m.inject_serial_rx(B("01 02 03"))
    r = iss.serial_io(m, b"x")
    assert (r.ack, r.tx_count, r.rx) == (False, 30, B("01 02 03"))


def test_mock_serial_works_in_i2c_serial():
    m = MockTransport(mode=0x40)
    iss.set_mode(m, iss.build_i2c_serial(iss.I2C_S_100KHZ, 9600))
    assert iss.serial_io(m, b"hi").ack
    assert bytes(m.serial_sent) == b"hi"


def test_mock_serial_io_outside_serial_mode():
    m = MockTransport(mode=0x40)
    with pytest.raises(iss.IssTimeout):
        iss.serial_io(m, b"hi")
    assert m.unhandled == [B("62") + b"hi"]


def test_mock_serial_payload_5a01_is_data():
    m = serial_mock()
    assert iss.serial_io(m, B("5A 01")).ack
    assert bytes(m.serial_sent) == B("5A 01")
    assert m.read(3) == b""
