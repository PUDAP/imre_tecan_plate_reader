"""Connection-only diagnostic for the Tecan Infinite 200 PRO."""

from __future__ import annotations

import asyncio
import logging
import traceback

import libusb_package
import usb.core
import usb.util
from pylabrobot.plate_reading import PlateReader
from pylabrobot.plate_reading.tecan import ExperimentalTecanInfinite200ProBackend


VID = 0x0C47
PID = 0x8007


async def diagnose() -> int:
    print("[1/4] Loading the packaged libusb backend...", flush=True)
    usb_backend = libusb_package.get_libusb1_backend()
    if usb_backend is None:
        print("FAIL: libusb-package did not provide a backend.", flush=True)
        return 1

    print("[2/4] Looking for USB device 0C47:8007...", flush=True)
    device = usb.core.find(backend=usb_backend, idVendor=VID, idProduct=PID)
    if device is None:
        print("FAIL: the Tecan USB device was not found.", flush=True)
        return 1
    print(
        f"PASS: found serial={device.serial_number!r}, "
        f"bus={device.bus}, address={device.address}",
        flush=True,
    )
    usb.util.dispose_resources(device)

    print("[3/4] Starting the PyLabRobot reader handshake...", flush=True)
    reader = PlateReader(
        name="diagnostic_reader",
        size_x=0,
        size_y=0,
        size_z=0,
        backend=ExperimentalTecanInfinite200ProBackend(
            counts_per_mm_x=1000,
            counts_per_mm_y=1000,
            counts_per_mm_z=1000,
        ),
    )
    setup_complete = False
    try:
        await asyncio.wait_for(reader.setup(), timeout=120)
        setup_complete = True
        print("[4/4] PASS: PyLabRobot initialization completed.", flush=True)
        return 0
    except BaseException as exc:
        print(
            f"FAIL during PyLabRobot setup: {type(exc).__name__}: {exc!s}",
            flush=True,
        )
        traceback.print_exc()
        return 1
    finally:
        if setup_complete:
            try:
                await reader.stop()
            except Exception as exc:
                print(
                    f"WARNING: setup passed but disconnect failed: "
                    f"{type(exc).__name__}: {exc!s}",
                    flush=True,
                )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    raise SystemExit(asyncio.run(diagnose()))
