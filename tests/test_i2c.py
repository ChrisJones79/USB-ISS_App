"""Iteration 03: I2C_SGL, I2C_AD0, I2C_AD1, I2C_AD2, I2C_TEST (datasheet pp.11-16; D-006)."""
import pytest

from usb_iss_app import iss
from usb_iss_app.mock import MockI2cDevice, MockTransport

B = bytes.fromhex


def test_constants():
    assert (iss.I2C_SGL, iss.I2C_AD0, iss.I2C_AD1, iss.I2C_AD2, iss.I2C_TEST) == (0x53, 0x54, 0x55, 0x56, 0x58)
    assert (iss.I2C_AD0_MAX, iss.I2C_AD1_MAX, iss.I2C_AD2_WRITE_MAX, iss.I2C_AD2_READ_MAX) == (60, 60, 59, 64)


# ---- datasheet example frames ----
def test_sgl_examples():
    assert iss.build_i2c_sgl_write(0x40, 0x00) == B("53 40 00")  # p.11
    assert iss.build_i2c_sgl_read(0x40) == B("53 41")  # p.12


def test_ad0_examples():
    assert iss.build_i2c_ad0_read(0xF0, 2) == B("54 F1 02")  # p.12
    # p.12 shows count 02 with four data bytes; D-006: the text wins, the count is 04.
    assert iss.build_i2c_ad0_write(0x30, B("12 34 56 78")) == B("54 30 04 12 34 56 78")


def test_ad1_examples():
    assert iss.build_i2c_ad1_write(0xE0, 0x00, B("AB")) == B("55 E0 00 01 AB")  # p.13, nn = AB
    assert iss.build_i2c_ad1_read(0xC0, 0x02, 2) == B("55 C1 02 02")  # p.13


def test_ad2_examples():
    data = bytes(range(32))
    # p.14 shows count 34 for 32 data bytes in a "37 byte sequence"; D-006: the count is 0x20.
    frame = iss.build_i2c_ad2_write(0xA0, 0x0000, data)
    assert frame == B("56 A0 00 00 20") + data and len(frame) == 37
    assert iss.build_i2c_ad2_read(0xA0, 0x0000, 3) == B("56 A1 00 00 03")  # p.14


def test_test_example():
    assert iss.build_i2c_test(0xA0) == B("58 A0")  # p.16


def test_ad2_register_high_byte_first():
    assert iss.build_i2c_ad2_write(0xA0, 0x1234, B("01")) == B("56 A0 12 34 01 01")
    assert iss.build_i2c_ad2_read(0xA0, 0x1234, 1) == B("56 A1 12 34 01")


# ---- limits ----
@pytest.mark.parametrize("build,limit", [
    (lambda n: iss.build_i2c_ad0_write(0x40, bytes(n)), 60),
    (lambda n: iss.build_i2c_ad0_read(0x40, n), 60),
    (lambda n: iss.build_i2c_ad1_write(0x40, 0, bytes(n)), 60),
    (lambda n: iss.build_i2c_ad1_read(0x40, 0, n), 60),
    (lambda n: iss.build_i2c_ad2_write(0x40, 0, bytes(n)), 59),
    (lambda n: iss.build_i2c_ad2_read(0x40, 0, n), 64),
])
def test_limit_boundaries(build, limit):
    build(limit)
    build(1)
    for bad in (limit + 1, 0):
        with pytest.raises(ValueError):
            build(bad)


@pytest.mark.parametrize("addr", [0x41, 0xFF, 0x100, -2, 0x01])
def test_bad_addresses(addr):
    for f in (lambda: iss.build_i2c_sgl_write(addr, 0), lambda: iss.build_i2c_sgl_read(addr),
              lambda: iss.build_i2c_ad0_write(addr, b"\0"), lambda: iss.build_i2c_ad0_read(addr, 1),
              lambda: iss.build_i2c_ad1_write(addr, 0, b"\0"), lambda: iss.build_i2c_ad1_read(addr, 0, 1),
              lambda: iss.build_i2c_ad2_write(addr, 0, b"\0"), lambda: iss.build_i2c_ad2_read(addr, 0, 1),
              lambda: iss.build_i2c_test(addr)):
        with pytest.raises(ValueError):
            f()


def test_address_extremes_ok():
    assert iss.build_i2c_test(0x00) == B("58 00")
    assert iss.build_i2c_test(0xFE) == B("58 FE")
    assert iss.build_i2c_sgl_read(0xFE) == B("53 FF")


def test_bad_registers_and_values():
    with pytest.raises(ValueError):
        iss.build_i2c_ad1_write(0x40, 256, b"\0")
    with pytest.raises(ValueError):
        iss.build_i2c_ad1_read(0x40, 256, 1)
    with pytest.raises(ValueError):
        iss.build_i2c_ad2_write(0x40, 0x10000, b"\0")
    with pytest.raises(ValueError):
        iss.build_i2c_ad2_read(0x40, 0x10000, 1)
    with pytest.raises(ValueError):
        iss.build_i2c_ad1_write(0x40, -1, b"\0")
    with pytest.raises(ValueError):
        iss.build_i2c_sgl_write(0x40, 256)


# ---- parsers ----
def test_parse_write():
    with pytest.raises(iss.IssNack, match="I2C_AD1 NACK") as e:
        iss.parse_i2c_write(B("00"), "I2C_AD1")
    assert e.value.reason is None
    iss.parse_i2c_write(B("01"), "I2C_AD1")
    iss.parse_i2c_write(B("FF"), "I2C_AD1")
    with pytest.raises(iss.IssTimeout):
        iss.parse_i2c_write(b"", "I2C_AD1")


def test_parse_read():
    assert iss.parse_i2c_read(B("01 02 03"), 2) == B("01 02")
    with pytest.raises(iss.IssTimeout):
        iss.parse_i2c_read(B("01"), 2)


def test_parse_test():
    assert iss.parse_i2c_test(B("00")) is False
    assert iss.parse_i2c_test(B("01")) is True
    assert iss.parse_i2c_test(B("FF")) is True
    with pytest.raises(iss.IssTimeout):
        iss.parse_i2c_test(b"")


# ---- mock bus ----
def bus(devices=None):
    m = MockTransport(mode=0x40)
    m.i2c_devices = dict(devices or {})
    return m


def test_mock_default_bus_empty():
    assert MockTransport().i2c_devices == {}


def test_mock_ad1_roundtrip():
    m = bus({0xA0: MockI2cDevice()})
    iss.i2c_ad1_write(m, 0xA0, 0x10, B("DE AD BE EF"))
    assert iss.i2c_ad1_read(m, 0xA0, 0x10, 4) == B("DE AD BE EF")
    assert m.i2c_devices[0xA0].mem[0x10:0x14] == B("DE AD BE EF")


def test_mock_ad2_high_register():
    m = bus({0xA0: MockI2cDevice(size=0x10000)})
    iss.i2c_ad2_write(m, 0xA0, 0x0100, B("11 22"))
    assert m.i2c_devices[0xA0].mem[0x0100:0x0102] == B("11 22")
    assert m.i2c_devices[0xA0].mem[0x0001] == 0
    assert iss.i2c_ad2_read(m, 0xA0, 0x0100, 2) == B("11 22")


def test_mock_ad0_continues_after_ad1():
    m = bus({0xA0: MockI2cDevice()})
    m.i2c_devices[0xA0].mem[:6] = B("00 01 02 03 04 05")
    assert iss.i2c_ad1_read(m, 0xA0, 0, 2) == B("00 01")
    assert iss.i2c_ad0_read(m, 0xA0, 2) == B("02 03")


def test_mock_ad0_write_at_pointer_and_wrap():
    d = MockI2cDevice(size=4)
    m = bus({0xA0: d})
    iss.i2c_ad1_write(m, 0xA0, 3, B("AA"))
    iss.i2c_ad0_write(m, 0xA0, B("BB CC"))  # pointer wrapped to 0
    assert d.mem == B("BB CC 00 AA") and d.pointer == 2


def test_mock_sgl():
    d = MockI2cDevice()
    m = bus({0x40: d})
    iss.i2c_sgl_write(m, 0x40, 0x5A)
    d.pointer = 0
    assert iss.i2c_sgl_read(m, 0x40) == 0x5A


def test_mock_absent_address():
    m = bus()
    for f in (lambda: iss.i2c_sgl_write(m, 0x40, 1), lambda: iss.i2c_ad0_write(m, 0x40, b"\1"),
              lambda: iss.i2c_ad1_write(m, 0x40, 0, b"\1"), lambda: iss.i2c_ad2_write(m, 0x40, 0, b"\1")):
        with pytest.raises(iss.IssNack):
            f()
    assert iss.i2c_sgl_read(m, 0x40) == 0xFF
    assert iss.i2c_ad0_read(m, 0x40, 3) == B("FF FF FF")
    assert iss.i2c_ad1_read(m, 0x40, 0, 3) == B("FF FF FF")
    assert iss.i2c_ad2_read(m, 0x40, 0, 3) == B("FF FF FF")
    assert iss.i2c_test(m, 0x40) is False
    assert iss.version(m).module_id == 7


def test_mock_present_test():
    m = bus({0x40: MockI2cDevice()})
    assert iss.i2c_test(m, 0x40) is True
    assert iss.i2c_test(m, 0x42) is False


def test_mock_split_frame_waits():
    m = bus({0xA0: MockI2cDevice()})
    frame = iss.build_i2c_ad1_write(0xA0, 5, B("01 02 03"))
    m.write(frame[:5])
    assert m.read(1) == b""
    m.write(frame[5:])
    assert m.read(1) == B("FF")
    assert m.i2c_devices[0xA0].mem[5:8] == B("01 02 03")


def test_mock_data_5a_01_is_not_a_command():
    m = bus({0xA0: MockI2cDevice()})
    iss.i2c_ad1_write(m, 0xA0, 0, B("5A 01"))
    assert m.read(3) == b""
    assert iss.i2c_ad1_read(m, 0xA0, 0, 2) == B("5A 01")
    assert m.unhandled == []


def test_mock_i2c_serial_mode():
    m = bus({0xA0: MockI2cDevice()})
    iss.set_mode(m, iss.build_i2c_serial(iss.I2C_S_100KHZ, 9600))
    iss.i2c_ad1_write(m, 0xA0, 1, B("77"))
    assert iss.i2c_ad1_read(m, 0xA0, 1, 1) == B("77")
    assert iss.i2c_test(m, 0xA0) is True


def test_mock_io_mode_consumes_frame():
    m = bus({0xA0: MockI2cDevice()})
    iss.set_mode(m, iss.build_io_mode(0xAA))
    # Hardware: IO_MODE answers I2C_TEST with 00 (iteration 03 logs build-hw-20261017-233218, review-hw-20261018-001847).
    assert iss.i2c_test(m, 0xA0) is False
    assert m.unhandled == []
    m.write(iss.build_i2c_ad1_write(0xA0, 0, B("5A 01")))
    assert m.read(1) == b""
    assert m.unhandled[-1] == B("55 A0 00 02 5A 01")
    assert iss.version(m).mode == 0x00


def test_mock_io_serial_mode_i2c_test_unanswered():
    m = bus({0xA0: MockI2cDevice()})
    iss.set_mode(m, iss.build_io_serial(9600, 0xAA))
    with pytest.raises(iss.IssTimeout):
        iss.i2c_test(m, 0xA0)
    assert m.unhandled == [B("58 A0")]
