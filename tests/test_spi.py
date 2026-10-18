"""Iteration 05: SPI (datasheet pp.17-18; D-007)."""
import pytest

from usb_iss_app import iss
from usb_iss_app.mock import MockSpiDevice, MockTransport

B = bytes.fromhex


def test_constants():
    assert (iss.SPI_IO, iss.SPI_FRAME_MAX, iss.SPI_DATA_MAX) == (0x61, 63, 62)


# ---- builder: datasheet examples ----
def test_example_wrsr():  # p.17
    assert iss.build_spi_io(B("01 41")) == B("61 01 41")


def test_example_write():  # p.18
    assert iss.build_spi_io(B("02 00 00 12 34 56 78")) == B("61 02 00 00 12 34 56 78")


def test_example_read():  # p.18, dummy bytes "any" = FF
    assert iss.build_spi_io(B("03 00 00 FF FF FF FF")) == B("61 03 00 00 FF FF FF FF")


def test_limits():
    assert len(iss.build_spi_io(bytes(62))) == 63
    for n in (0, 63):
        with pytest.raises(ValueError):
            iss.build_spi_io(bytes(n))


# ---- parser ----
def test_parse_ack():
    assert iss.parse_spi_response(B("FF 12 34"), 2) == B("12 34")


@pytest.mark.parametrize("resp", [B("00"), B("00 12 34")])
def test_parse_nack(resp):
    with pytest.raises(iss.IssNack) as e:
        iss.parse_spi_response(resp, 2)
    assert e.value.reason is None and str(e.value) == "SPI NACK"


@pytest.mark.parametrize("resp", [b"", B("FF 12")])
def test_parse_timeout(resp):
    with pytest.raises(iss.IssTimeout):
        iss.parse_spi_response(resp, 2)


def test_parse_protocol_error():
    with pytest.raises(iss.IssProtocolError):
        iss.parse_spi_response(B("7F 00 00"), 2)


# ---- helper ----
class _Rec(MockTransport):
    """Records write() and read() calls and answers with a canned reply."""
    def __init__(self, reply):
        super().__init__(mode=0x90)
        self.reply = reply
        self.writes = []
        self.reads = []

    def write(self, data):
        self.writes.append(bytes(data))
        self._rx += self.reply

    def read(self, n, timeout=0.5):
        self.reads.append(n)
        return super().read(n)


def test_helper_one_write_one_read():
    t = _Rec(B("FF 12 34"))
    assert iss.spi_io(t, B("01 02")) == B("12 34")
    assert t.writes == [B("61 01 02")]
    assert t.reads == [3]


def test_helper_short_reply_times_out():
    with pytest.raises(iss.IssTimeout):
        iss.spi_io(_Rec(B("FF 12")), B("01 02"))


# ---- mock ----
class Sram23K256(MockSpiDevice):
    def __init__(self):
        self.mem = bytearray(0x8000)
        self.status = 0x00
        self.seen = []

    def transfer(self, data):
        self.seen.append(bytes(data))
        out = bytearray(b"\xff" * len(data))
        cmd = data[0]
        if cmd == 0x01 and len(data) > 1:
            self.status = data[1]
        elif cmd in (0x02, 0x03) and len(data) >= 3:
            addr = data[1] << 8 | data[2]
            for i, b in enumerate(data[3:], start=3):
                if cmd == 0x02:
                    self.mem[addr % 0x8000] = b
                else:
                    out[i] = self.mem[addr % 0x8000]
                addr += 1
        return bytes(out)


def spi(mode=0x90, device=None):
    m = MockTransport(mode=mode)
    m.spi_device = device
    return m


def test_mock_23k256_sequence():
    d = Sram23K256()
    m = spi(device=d)
    iss.set_mode(m, iss.build_spi_mode(0, 500_000))
    assert len(iss.spi_io(m, B("01 41"))) == 2 and d.status == 0x41
    assert len(iss.spi_io(m, B("02 00 00 12 34 56 78"))) == 7
    got = iss.spi_io(m, B("03 00 00 FF FF FF FF"))
    assert len(got) == 7 and got[-4:] == B("12 34 56 78")
    assert d.mem[0:4] == B("12 34 56 78")


def test_mock_one_frame_one_transfer():
    d = Sram23K256()
    m = spi(device=d)
    iss.spi_io(m, B("02 00 00 12 34 56 78"))
    assert d.seen == [B("02 00 00 12 34 56 78")]


def test_mock_no_device():
    assert iss.spi_io(spi(), B("01 02 03")) == B("FF FF FF")


def test_mock_base_device_returns_ff():
    assert iss.spi_io(spi(device=MockSpiDevice()), B("01 02")) == B("FF FF")


def test_mock_raw_62_data_bytes():
    d = Sram23K256()
    m = spi(device=d)
    m.write(b"\x61" + bytes(62))
    assert m.read(100) == b"\xff" * 63
    assert len(d.seen) == 1 and len(d.seen[0]) == 62


def test_mock_raw_63_data_bytes_nack():
    d = Sram23K256()
    m = spi(device=d)
    m.write(b"\x61" + bytes(63))
    assert m.read(100) == B("00")
    assert d.seen == []


def test_mock_raw_61_alone():
    d = Sram23K256()
    m = spi(device=d)
    m.write(b"\x61")
    assert m.read(100) == B("FF")
    assert d.seen == []


def test_mock_command_bytes_inside_data():
    d = Sram23K256()
    m = spi(device=d)
    assert iss.spi_io(m, B("5A 01")) == B("FF FF")
    assert d.seen == [B("5A 01")]
    assert m.unhandled == []
    assert m.read(10) == b""


@pytest.mark.parametrize("mode", [0x90, 0x91, 0x92, 0x93])
def test_mock_all_phases(mode):
    d = Sram23K256()
    m = spi(mode=mode, device=d)
    iss.spi_io(m, B("02 00 05 AB"))
    assert d.mem[5] == 0xAB


@pytest.mark.parametrize("frame", [
    iss.build_i2c_mode(iss.I2C_S_100KHZ, 0xAA),
    iss.build_io_mode(0xAA),
    iss.build_io_serial(9600, 0xAA),
    iss.build_i2c_serial(iss.I2C_S_100KHZ, 9600),
])
def test_mock_outside_spi_mode(frame):
    d = Sram23K256()
    m = spi(mode=0x40, device=d)
    iss.set_mode(m, frame)
    mode = iss.version(m).mode
    with pytest.raises(iss.IssTimeout):
        iss.spi_io(m, B("01 02"))
    assert m.unhandled == [B("61 01 02")]
    assert iss.version(m).mode == mode
    assert d.seen == []


def test_mock_i2c_serial_h100_still_settable():
    # The 5A 02 61 .. frame is I2C_H_100KHZ+SERIAL (p.9), not SPI.
    m = spi(mode=0x40)
    iss.set_mode(m, iss.build_i2c_serial(iss.I2C_H_100KHZ, 9600))
    assert iss.version(m).mode == 0x61
    assert m.unhandled == []
