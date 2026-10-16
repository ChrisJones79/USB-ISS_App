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
