# USB-ISS Interface

A small project written with the help of Claude Code.

A graphical interface for getting and setting USB-ISS options and
interacting with downstream devices via serial, I2C, or SPI. 

## Downstream Devices

Cards are created for devices which contain configuration info
for the USB-ISS and contain a device specific component that is
loaded into the USB-ISS interface. Once a card is created for a
particular device, it can be recalled and loaded to the interface.

Card creation is handled through the interface and includes the
device configuration, plus any graphical or tabular components
that allow a user to access device functionality and configuration.

## Setup

```bash
pyenv install -s 3.12.15
pyenv local 3.12.15          # already pinned in .python-version
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env         # then set USB_ISS_PORT=/dev/serial/by-id/<your device>
```

Run the tests (logs go to `docs/iterations/NN/logs/`):

```bash
python scripts/run_tests.py --iter 00 --tag build          # mock only
python scripts/run_tests.py --iter 00 --tag build --hw     # also real USB-ISS
```
