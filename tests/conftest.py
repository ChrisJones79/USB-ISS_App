import pytest

from usb_iss_app.mock import MockTransport
from usb_iss_app.transport import SerialTransport


def pytest_collection_modifyitems(config, items):
    if config.getoption("--hw", default=False):
        return
    skip = pytest.mark.skip(reason="hardware test; use --hw")
    for item in items:
        if "hw" in item.keywords:
            item.add_marker(skip)


def pytest_addoption(parser):
    parser.addoption("--hw", action="store_true", default=False, help="run hardware tests")


@pytest.fixture
def mock():
    return MockTransport()


@pytest.fixture
def hw():
    t = SerialTransport()
    yield t
    t.close()
