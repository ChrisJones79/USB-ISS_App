import inspect

import pytest

from usb_iss_app import iss, transport
from usb_iss_app.mock import MockTransport

B = bytes.fromhex


# ---- requirement 1: decode_mode ----
@pytest.mark.parametrize("b,name", [
    (0x00, "IO_MODE"), (0x01, "IO_MODE+SERIAL"), (0x20, "I2C_S_20KHZ"), (0x30, "I2C_S_50KHZ"),
    (0x40, "I2C_S_100KHZ"), (0x50, "I2C_S_400KHZ"), (0x60, "I2C_H_100KHZ"),
    (0x70, "I2C_H_400KHZ"), (0x80, "I2C_H_1000KHZ"), (0x61, "I2C_H_100KHZ+SERIAL"),
    (0x21, "I2C_S_20KHZ+SERIAL"), (0x81, "I2C_H_1000KHZ+SERIAL"),
    (0x90, "SPI_MODE phase 0"), (0x92, "SPI_MODE phase 2"), (0x93, "SPI_MODE phase 3"),
])
def test_decode_mode(b, name):
    assert iss.decode_mode(b) == name


@pytest.mark.parametrize("b", [0x02, 0x11, 0x41 + 0x01, 0x94, 0xFF, 0xA0])
def test_decode_unknown(b):
    assert iss.decode_mode(b) == f"UNKNOWN(0x{b:02X})"


def test_mode_constants():
    assert (iss.IO_MODE, iss.IO_CHANGE, iss.SERIAL, iss.SPI_MODE) == (0x00, 0x10, 0x01, 0x90)
    assert [iss.I2C_S_20KHZ, iss.I2C_S_50KHZ, iss.I2C_S_100KHZ, iss.I2C_S_400KHZ,
            iss.I2C_H_100KHZ, iss.I2C_H_400KHZ, iss.I2C_H_1000KHZ] == [
        0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80]


# ---- requirement 2: IO_TYPE ----
def test_io_type_examples():
    L, H, D, A = iss.IoType.OUTPUT_LOW, iss.IoType.OUTPUT_HIGH, iss.IoType.DIGITAL_INPUT, iss.IoType.ANALOGUE_INPUT
    assert iss.io_type(H, L, L, L) == 0x01
    assert iss.io_type(L, H, A, D) == 0xB4
    assert iss.io_type(D, D, L, L) == 0x0A
    assert iss.io_type(A, A, L, L) == 0x0F
    assert iss.io_type(D, D, D, D) == 0xAA


def test_io_type_rejects_bad_pin():
    with pytest.raises(ValueError):
        iss.io_type(4, 0, 0, 0)


# ---- requirement 3: divisors ----
@pytest.mark.parametrize("bps,div,hi,lo", [
    (300, 9999, 0x27, 0x0F), (1200, 2499, 0x09, 0xC3), (2400, 1249, 0x04, 0xE1),
    (9600, 311, 0x01, 0x37), (19200, 155, 0x00, 0x9B), (38400, 77, 0x00, 0x4D),
    (57600, 51, 0x00, 0x33), (115200, 25, 0x00, 0x19),
])
def test_baud_table(bps, div, hi, lo):
    assert iss.baud_divisor(bps)[0] == div
    assert (div >> 8, div & 0xFF) == (hi, lo)
    assert iss.build_io_serial(bps, 0xB0) == bytes([0x5A, 0x02, 0x01, hi, lo, 0xB0])


def test_baud_115200():
    d, actual, err = iss.baud_divisor(115200)
    assert d == 25
    assert round(actual) == 115385
    assert err == pytest.approx(0.16, abs=0.005)


@pytest.mark.parametrize("bps", [460800, 1, 10_000_000, 0, -9600])
def test_baud_refused(bps):
    with pytest.raises(ValueError):
        iss.build_io_serial(bps, 0)
    with pytest.raises(ValueError):
        iss.build_i2c_serial(iss.I2C_H_100KHZ, bps)


@pytest.mark.parametrize("sck,div", [(3_000_000, 1), (500_000, 11), (23437.5, 255)])
def test_spi_divisor(sck, div):
    d, actual, err = iss.spi_divisor(sck)
    assert d == div
    assert actual <= sck + 1e-9  # D-005: never above the request
    assert err == pytest.approx((actual - sck) / sck * 100)


def test_spi_divisor_rounds_down_in_frequency():
    d, actual, err = iss.spi_divisor(1_000_000)  # 6e6/1e6 = 6 -> 5
    assert (d, actual) == (5, 1_000_000)
    d, actual, err = iss.spi_divisor(1_100_000)  # ceil(5.45)=6 -> 5, actual 1 MHz
    assert (d, actual) == (5, 1_000_000) and err < 0


@pytest.mark.parametrize("sck", [4_000_000, 20_000, 0, -1, 23437.4])
def test_spi_refused(sck):
    with pytest.raises(ValueError):
        iss.spi_divisor(sck)
    with pytest.raises(ValueError):
        iss.build_spi_mode(0, sck)


# ---- requirement 4: frames ----
def test_frames_datasheet_examples():
    assert iss.build_io_mode(0xB4) == B("5A 02 00 B4")
    assert iss.build_io_change(0xB4) == B("5A 02 10 B4")
    assert iss.build_io_serial(19200, 0xB0) == B("5A 02 01 00 9B B0")
    assert iss.build_i2c_mode(iss.I2C_H_100KHZ, 0x04) == B("5A 02 60 04")
    assert iss.build_i2c_serial(iss.I2C_H_100KHZ, 19200) == B("5A 02 61 00 9B")
    assert iss.build_spi_mode(0, 3_000_000) == B("5A 02 90 01")


def test_spi_frame_phase_and_divisor():
    assert iss.build_spi_mode(3, 500_000) == B("5A 02 93 0B")


@pytest.mark.parametrize("mode", [iss.IO_MODE, iss.IO_CHANGE, iss.SPI_MODE, 0x61, 0x10, 0x90, 0x100, -1])
def test_i2c_builders_reject_non_i2c(mode):
    with pytest.raises(ValueError):
        iss.build_i2c_mode(mode, 0)
    with pytest.raises(ValueError):
        iss.build_i2c_serial(mode, 19200)


@pytest.mark.parametrize("phase", [-1, 4])
def test_spi_phase_rejected(phase):
    with pytest.raises(ValueError):
        iss.build_spi_mode(phase, 500_000)


@pytest.mark.parametrize("bad", [-1, 256])
def test_io_type_byte_rejected(bad):
    with pytest.raises(ValueError):
        iss.build_io_mode(bad)


def test_parse_ok():
    assert iss.parse_mode_response(B("FF 00")) is None


@pytest.mark.parametrize("resp", [B("FF 01"), B("00 04"), B("00 00"), B("00 08"), B("01 00"), B("FE 00")])
def test_parse_protocol_error(resp):
    with pytest.raises(iss.IssProtocolError):
        iss.parse_mode_response(resp)


@pytest.mark.parametrize("resp", [b"", B("FF"), B("00")])
def test_parse_short(resp):
    with pytest.raises(iss.IssTimeout):
        iss.parse_mode_response(resp)


@pytest.mark.parametrize("reason,name", [(5, "Unknown command"), (6, "Internal Error 1"), (7, "Internal Error 2")])
def test_parse_nack(reason, name):
    with pytest.raises(iss.IssNack) as e:
        iss.parse_mode_response(bytes([0, reason]))
    assert e.value.reason == reason and e.value.name == name
    assert isinstance(e.value, iss.IssError)


def test_set_mode_writes_frame_and_reads_two():
    class T:
        sent, n = b"", None

        def write(self, d):
            self.sent += d

        def read(self, n, timeout=0.5):
            self.n = n
            return B("FF 00")

    t = T()
    iss.set_mode(t, iss.build_io_mode(0xAA))
    assert t.sent == B("5A 02 00 AA") and t.n == 2


def test_set_mode_short_response():
    class T:
        def write(self, d): pass
        def read(self, n, timeout=0.5): return B("FF")

    with pytest.raises(iss.IssTimeout):
        iss.set_mode(T(), B("5A 02 00 AA"))


# ---- requirement 5: mock ----
def test_mock_io_serial_framing_ignores_payload_bytes(mock):
    mock.write(B("5A 02 01 5A 01 B0"))
    assert mock.read(16) == B("FF 00")  # no ISS_VERSION reply
    assert mock.unhandled == []
    assert mock.mode == 0x01


def test_mock_waits_for_whole_frame(mock):
    for part in ("5A", "02", "01", "00", "9B"):
        mock.write(B(part))
        assert mock.read(4) == b""
    mock.write(B("B0"))
    assert mock.read(4) == B("FF 00")


@pytest.mark.parametrize("frame,mode", [
    (iss.build_io_mode(0xAA), 0x00),
    (iss.build_io_serial(19200, 0xB0), 0x01),
    (iss.build_i2c_mode(iss.I2C_S_400KHZ, 0x0A), 0x50),
    (iss.build_i2c_serial(iss.I2C_H_1000KHZ, 9600), 0x81),
    (iss.build_spi_mode(2, 500_000), 0x92),
])
def test_mock_mode_set_reflected_in_version(mock, frame, mode):
    iss.set_mode(mock, frame)
    assert iss.version(mock).mode == mode
    assert mock.unhandled == []


def test_mock_io_change_keeps_mode(mock):
    iss.set_mode(mock, iss.build_io_change(0x0F))
    assert iss.version(mock).mode == 0x40


def test_mock_unknown_mode_nack(mock):
    mock.write(B("5A 02 05"))
    assert mock.read(8) == B("00 05")
    assert iss.version(mock).mode == 0x40  # unchanged, and nothing left over
    assert iss.serial_number(mock) == "00000001"


@pytest.mark.parametrize("reason", [6, 7])
def test_mock_forced_nack_through_set_mode(mock, reason):
    mock.force_next_mode_nack(reason)
    with pytest.raises(iss.IssNack) as e:
        iss.set_mode(mock, iss.build_io_mode(0xAA))
    assert e.value.reason == reason
    assert iss.version(mock).mode == 0x40  # NACK does not change mode
    iss.set_mode(mock, iss.build_io_mode(0xAA))  # hook is one-shot
    assert iss.version(mock).mode == 0x00


def test_mock_unknown_nack_reason_5_through_set_mode(mock):
    with pytest.raises(iss.IssNack) as e:
        iss.set_mode(mock, B("5A 02 05 00"))
    assert e.value.reason == 5


def test_mock_unknown_subcommand_still_dropped(mock):
    mock.write(B("5A 7F"))
    assert mock.read(4) == b"" and mock.unhandled == [B("5A 7F")]


# ---- requirements 6 and 7: timeouts ----
def test_default_timeout_is_500ms():
    assert transport.DEFAULT_TIMEOUT == 0.5
    for fn in (transport.Transport.read, MockTransport.read, transport.SerialTransport.__init__):
        assert inspect.signature(fn).parameters["timeout"].default in (0.5, None)
    assert inspect.signature(transport.SerialTransport.__init__).parameters["timeout"].default == 0.5


def _fake_serial(monkeypatch):
    import serial

    class FakeSerial:
        def __init__(self, port, timeout=None):
            self.timeout = timeout
            self.seen = []

        def reset_input_buffer(self): pass

        def read(self, n):
            self.seen.append(self.timeout)
            return b""

    monkeypatch.setattr(serial, "Serial", FakeSerial)


def test_serial_transport_constructor_timeout_applies(monkeypatch):
    _fake_serial(monkeypatch)
    t = transport.SerialTransport("/dev/fake", timeout=2.0)
    t.read(1)
    t.read(1, timeout=0.1)
    t.read(1)
    assert t._ser.seen == [2.0, 0.1, 2.0]


def test_serial_transport_default_timeout(monkeypatch):
    _fake_serial(monkeypatch)
    t = transport.SerialTransport("/dev/fake")
    t.read(1)
    assert t._ser.seen == [0.5]
