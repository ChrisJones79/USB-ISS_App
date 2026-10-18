"""Iteration 04: I2C_DIRECT (datasheet pp.15-16; D-007)."""
import pytest

from usb_iss_app import iss
from usb_iss_app.mock import MockI2cDevice, MockTransport

B = bytes.fromhex
STOP = iss.I2C_DIRECT_STOP


def test_constants():
    assert iss.I2C_DIRECT == 0x57
    assert (iss.I2C_DIRECT_START, iss.I2C_DIRECT_RESTART, iss.I2C_DIRECT_STOP, iss.I2C_DIRECT_NACK) == (1, 2, 3, 4)
    assert (iss.I2C_DIRECT_FRAME_MAX, iss.I2C_DIRECT_CHUNK_MAX, iss.I2C_DIRECT_READ_TOTAL_MAX) == (59, 16, 60)
    assert iss.I2C_DIRECT_NACK_REASONS == {1: "Device Error", 2: "Buffer Overflow", 3: "Buffer Underflow", 4: "Unknown command"}


# ---- builders: datasheet examples ----
def test_example_pcf8574_write():  # p.15
    assert iss.build_i2c_direct(1, iss.direct_write(B("40 55")), 3) == B("57 01 31 40 55 03")


def test_example_24lc512_write():  # p.16, nn nn = 12 34
    frame = iss.build_i2c_direct(1, iss.direct_write(B("A0 00 00 12 34")), 3)
    assert frame == B("57 01 34 A0 00 00 12 34 03")


def test_example_read_with_nack():  # p.16
    frame = iss.build_i2c_direct(1, iss.direct_write(B("A0 00 00")), 2, iss.direct_write(b"\xA1"),
                                 iss.direct_read(3), 4, iss.direct_read(1), 3)
    assert frame == B("57 01 32 A0 00 00 02 30 A1 22 04 20 03")
    assert iss.i2c_direct_read_count(frame) == 4


def test_example_read():  # p.16
    frame = iss.build_i2c_direct(1, iss.direct_write(B("A0 00 00")), 2, iss.direct_write(b"\xA1"),
                                 iss.direct_read(4), 3)
    assert frame == B("57 01 32 A0 00 00 02 30 A1 23 03")
    assert iss.i2c_direct_read_count(frame) == 4


# ---- limits ----
def test_direct_read_limits():
    assert iss.direct_read(1) == B("20") and iss.direct_read(16) == B("2F")
    for n in (0, 17):
        with pytest.raises(ValueError):
            iss.direct_read(n)


def test_direct_write_limits():
    assert iss.direct_write(b"\1") == B("30 01")
    assert iss.direct_write(bytes(16)) == B("3F") + bytes(16)
    for data in (b"", bytes(17)):
        with pytest.raises(ValueError):
            iss.direct_write(data)


def test_frame_length_boundary():
    assert len(iss.build_i2c_direct(*[STOP] * 58)) == 59
    with pytest.raises(ValueError):
        iss.build_i2c_direct(*[STOP] * 59)


def test_total_read_boundary():
    r = iss.direct_read
    frame = iss.build_i2c_direct(r(16), r(16), r(16), r(12))
    assert iss.i2c_direct_read_count(frame) == 60
    with pytest.raises(ValueError):
        iss.build_i2c_direct(r(16), r(16), r(16), r(13))


@pytest.mark.parametrize("parts", [(), (0x00,), (0x05,), (0x1F,), (0x40,), (256,), (-1,),
                                   (0x31, b"\x40"), (0x30,)])
def test_refused_frames(parts):
    with pytest.raises(ValueError):
        iss.build_i2c_direct(*parts)


# ---- NACK names and parser ----
def test_parse_status_ack():
    assert iss.parse_i2c_direct_status(B("FF 00")) == 0
    assert iss.parse_i2c_direct_status(B("FF 04")) == 4


@pytest.mark.parametrize("rr,name", [(1, "Device Error"), (2, "Buffer Overflow"), (3, "Buffer Underflow"),
                                     (4, "Unknown command")])
def test_parse_status_nack(rr, name):
    with pytest.raises(iss.IssNack, match=f"I2C_DIRECT NACK: 0x{rr:02X} {name}") as e:
        iss.parse_i2c_direct_status(bytes([0, rr]))
    assert e.value.reason == rr and e.value.name == name


def test_parse_status_errors():
    for resp in (B("00"), b""):
        with pytest.raises(iss.IssTimeout):
            iss.parse_i2c_direct_status(resp)
    with pytest.raises(iss.IssProtocolError):
        iss.parse_i2c_direct_status(B("7F 00"))


def test_iss_mode_nack_names_unchanged():
    with pytest.raises(iss.IssNack, match="ISS_MODE NACK: 0x05 Unknown command"):
        iss.parse_mode_response(B("00 05"))
    assert "Internal Error 1" in str(iss.IssNack(6))


# ---- helper ----
class _Short(MockTransport):
    """Answers every I2C_DIRECT with a canned reply."""
    def __init__(self, reply):
        super().__init__(mode=0x40)
        self.reply = reply
        self.writes = []

    def write(self, data):
        self.writes.append(bytes(data))
        self._rx += self.reply


def test_helper_single_write():
    t = _Short(B("FF 00"))
    iss.i2c_direct(t, 1, iss.direct_write(B("40 55")), 3)
    assert t.writes == [B("57 01 31 40 55 03")]


def test_helper_short_data_times_out():
    with pytest.raises(iss.IssTimeout):
        iss.i2c_direct(_Short(B("FF 02 AA")), iss.direct_read(2))


def test_helper_count_mismatch_reads_everything():
    t = _Short(B("FF 03 01 02 03"))
    with pytest.raises(iss.IssProtocolError):
        iss.i2c_direct(t, iss.direct_read(2))
    assert t.read(1) == b""  # nothing left behind


# ---- mock ----
def bus(devices=None, mode=0x40):
    m = MockTransport(mode=mode)
    m.i2c_devices = dict(devices or {})
    return m


def write_frame(*data):
    return iss.build_i2c_direct(1, iss.direct_write(bytes(data)), 3)


def test_mock_pcf8574_write():
    d = MockI2cDevice(addr_bytes=0)
    m = bus({0x40: d})
    assert iss.i2c_direct(m, 1, iss.direct_write(B("40 55")), 3) == b""
    assert d.mem[0] == 0x55


def eeprom():
    d = MockI2cDevice(size=0x10000, addr_bytes=2)
    d.mem[2:4] = B("56 78")
    return d


def test_mock_24lc512_write_and_reads():
    d = eeprom()
    m = bus({0xA0: d})
    assert iss.i2c_direct(m, 1, iss.direct_write(B("A0 00 00 12 34")), 3) == b""
    assert d.mem[0:4] == B("12 34 56 78")
    sel = (1, iss.direct_write(B("A0 00 00")), 2, iss.direct_write(b"\xA1"))
    assert iss.i2c_direct(m, *sel, iss.direct_read(3), 4, iss.direct_read(1), 3) == B("12 34 56 78")
    assert iss.i2c_direct(m, *sel, iss.direct_read(4), 3) == B("12 34 56 78")


def test_mock_direct_write_read_back_by_ad1():
    m = bus({0xA0: MockI2cDevice(addr_bytes=1)})
    iss.i2c_direct(m, 1, iss.direct_write(B("A0 07 11 22")), 3)
    assert iss.i2c_ad1_read(m, 0xA0, 7, 2) == B("11 22")


def test_mock_partial_pointer_does_not_set_pointer():
    d = MockI2cDevice(size=0x10000, addr_bytes=2)
    d.pointer = 5
    m = bus({0xA0: d})
    iss.i2c_direct(m, 1, iss.direct_write(B("A0 12")), 3)
    assert d.pointer == 5


def test_mock_absent_address_nacks_reason_1():
    m = bus()
    with pytest.raises(iss.IssNack) as e:
        iss.i2c_direct(m, 1, iss.direct_write(b"\xA0"), 3)
    assert e.value.reason == 1


def test_mock_read_without_device_is_ff():
    m = bus()
    assert iss.i2c_direct(m, iss.direct_read(3)) == B("FF FF FF")


def test_mock_underflow():
    m = bus({0x40: MockI2cDevice()})
    m.write(B("57 01 31 40"))
    assert m.read(4) == B("00 03")


def test_mock_unknown_subcommand_is_ignored():
    # Hardware (build-hw-20261018-021131): 57 05 answers FF 00, not 00 04.
    m = bus()
    m.write(B("57 05"))
    assert m.read(4) == B("FF 00")


def test_mock_frame_length_boundary():
    m = bus()
    # Hardware (build-hw-20261018-021131): 60 bytes still answers FF 00, so the mock overflows at 61.
    m.write(B("57") + bytes([STOP]) * 60)
    assert m.read(4) == B("00 02")
    m.write(B("57") + bytes([STOP]) * 59)
    assert m.read(4) == B("FF 00")
    m.write(B("57") + bytes([STOP]) * 58)
    assert m.read(4) == B("FF 00")


def test_mock_overflow_executes_nothing():
    d = MockI2cDevice(addr_bytes=0)
    m = bus({0x40: d})
    m.write(B("57 01 31 40 55") + bytes([STOP]) * 56)  # 61 bytes
    assert m.read(4) == B("00 02")
    assert d.mem[0] == 0


def test_mock_split_frame():
    m = bus({0x40: MockI2cDevice()})
    m.write(B("57 01 31"))
    assert m.read(4) == B("00 03")
    # 40 is dropped; 55 03 then starts an I2C_AD1 frame, which stays pending like on the device.
    m.write(B("40 55 03"))
    assert m.read(4) == b""
    assert m.unhandled == [B("40")]


def test_mock_5a_01_is_data():
    d = MockI2cDevice(addr_bytes=0)
    m = bus({0x40: d})
    assert iss.i2c_direct(m, 1, iss.direct_write(B("40 5A 01")), 3) == b""
    assert d.mem[0:2] == B("5A 01")
    assert m.unhandled == [] and m.read(3) == b""


def test_mock_i2c_serial_mode():
    d = MockI2cDevice(addr_bytes=1)
    m = bus({0xA0: d})
    iss.set_mode(m, iss.build_i2c_serial(iss.I2C_S_100KHZ, 9600))
    iss.i2c_direct(m, 1, iss.direct_write(B("A0 03 99")), 3)
    assert d.mem[3] == 0x99


def test_mock_io_mode_answers_00():
    # Hardware (build-hw-20261018-021131): in IO_MODE, 57 01 30 A0 03 answers a single 00.
    m = bus({0x40: MockI2cDevice()})
    iss.set_mode(m, iss.build_io_mode(0xAA))
    m.write(B("57 01 30 40 03"))
    assert m.read(4) == B("00")
    with pytest.raises(iss.IssTimeout):
        iss.i2c_direct(m, 1, iss.direct_write(b"\x40"), 3)  # 00 alone is one status byte
    assert m.unhandled == []
    assert iss.version(m).mode == 0x00


def test_mock_io_serial_mode_consumes_frame():
    m = bus({0x40: MockI2cDevice()})
    iss.set_mode(m, iss.build_io_serial(9600, 0xAA))
    with pytest.raises(iss.IssTimeout):
        iss.i2c_direct(m, 1, iss.direct_write(b"\x40"), 3)
    assert m.unhandled == [B("57 01 30 40 03")]
    assert iss.version(m).mode == 0x01
