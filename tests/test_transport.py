from usb_iss_app.transport import find_port, parse_env_file


def test_env_parser(tmp_path):
    f = tmp_path / ".env"
    f.write_text('# c\nA=1\nUSB_ISS_PORT = "/dev/x"\n\nbad line\n')
    assert parse_env_file(f) == {"A": "1", "USB_ISS_PORT": "/dev/x"}


def test_find_port_env_wins(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("USB_ISS_PORT=/from/file\n")
    monkeypatch.setenv("USB_ISS_PORT", "/from/env")
    assert find_port(f) == "/from/env"
    monkeypatch.delenv("USB_ISS_PORT")
    assert find_port(f) == "/from/file"
    assert find_port(tmp_path / "missing") is None
