import pytest

from usb_iss_app import iss

pytestmark = pytest.mark.hw


def test_hw_version(hw):
    v = iss.version(hw)
    print(f"HW ISS_VERSION: module_id={v.module_id} firmware=0x{v.firmware:02X} mode=0x{v.mode:02X}")
    assert v.module_id == 7


def test_hw_serial(hw):
    s = iss.serial_number(hw)
    print(f"HW serial number: {s}")
    assert len(s) == 8 and s.isascii() and s.isdigit()


def test_hw_mode_sequence(hw):
    """NEXT 01 hardware sequence: inputs only, always restores I2C_S_100KHZ (0x40)."""
    def mode_byte(label):
        m = iss.version(hw).mode
        print(f"HW after {label}: mode=0x{m:02X} ({iss.decode_mode(m)})")
        return m

    try:
        iss.set_mode(hw, iss.build_i2c_mode(iss.I2C_S_100KHZ, 0x0A))
        assert mode_byte("I2C_S_100KHZ 5A 02 40 0A") == 0x40

        frame = iss.build_io_change(0x0F)
        hw.write(frame)
        raw = hw.read(2)
        print(f"HW IO_CHANGE {frame.hex(' ')} raw response: {raw.hex(' ') or '(none)'}")
        mode_byte("IO_CHANGE 5A 02 10 0F")  # logged, not asserted
        assert raw == bytes([0xFF, 0x00])

        iss.set_mode(hw, iss.build_io_mode(0xAA))
        assert mode_byte("IO_MODE 5A 02 00 AA") == 0x00
    finally:
        iss.set_mode(hw, iss.build_i2c_mode(iss.I2C_S_100KHZ, 0x0A))
        assert mode_byte("restore 5A 02 40 0A") == 0x40
