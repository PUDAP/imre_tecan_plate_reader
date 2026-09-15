"""PUDA driver for the Tecan Infinite 200 PRO plate reader."""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import Future
from typing import Any, Coroutine

from pylabrobot import resources
from pylabrobot.plate_reading import PlateReader
from pylabrobot.plate_reading.tecan import ExperimentalTecanInfinite200ProBackend
from pylabrobot.resources import Plate

logger = logging.getLogger(__name__)


class Tecan_Infinite_200_pro:
    """Control a Tecan Infinite 200 PRO M-series reader over USB.

    PyLabRobot exposes an asynchronous API while PUDA machine commands are
    synchronous.  The driver therefore owns one persistent asyncio loop in a
    worker thread.  Keeping a single loop is important because the backend's
    USB transport and asyncio locks must not move between event loops.

    Args:
        plate_model: Name of a PyLabRobot plate factory in
            :mod:`pylabrobot.resources`.
        counts_per_mm_x: Reader X-axis encoder counts per millimetre.
        counts_per_mm_y: Reader Y-axis encoder counts per millimetre.
        counts_per_mm_z: Reader Z-axis encoder counts per millimetre.
        command_timeout: Maximum seconds a PUDA call may wait for the reader.
    """

    def __init__(
        self,
        plate_model: str,
        counts_per_mm_x: float,
        counts_per_mm_y: float,
        counts_per_mm_z: float,
        command_timeout: float,
    ) -> None:
        if command_timeout <= 0:
            raise ValueError("command_timeout must be positive")

        self._plate_model = plate_model
        self._counts_per_mm = (counts_per_mm_x, counts_per_mm_y, counts_per_mm_z)
        self._command_timeout = command_timeout
        self._command_lock = threading.RLock()
        self._state_lock = threading.RLock()
        self._state = "starting"
        self._last_error: str | None = None
        self._tray_open = False
        self._reader: PlateReader | None = None
        self._plate: Plate | None = None

        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._run_event_loop,
            name="tecan-infinite-asyncio",
            daemon=True,
        )
        self._loop_thread.start()
        try:
            self._submit(self._setup())
        except Exception:
            self._stop_event_loop()
            raise

    def shutdown(self) -> bool:
        """Release the USB connection and stop the driver's worker thread.

        Returns:
            True when shutdown completed. Repeated calls are safe.
        """
        with self._command_lock:
            if not self._loop_thread.is_alive():
                return True
            try:
                self._submit(self._shutdown())
                return True
            finally:
                self._stop_event_loop()

    def home(self) -> bool:
        """Reinitialize the reader because it has no separate public home command.

        Returns:
            True when the PyLabRobot backend was stopped and set up again.
        """
        return self.reset()

    def reset(self) -> bool:
        """Reset the reader connection and leave the tray closed.

        Returns:
            True when reinitialization succeeds.
        """
        with self._command_lock:
            self._submit(self._reset())
        return True

    def open_tray(self) -> dict[str, Any]:
        """Open the plate-reader tray.

        Returns:
            A JSON-safe result containing ``success`` and ``tray_open``.
        """
        with self._command_lock:
            self._submit(self._open_tray())
        return {"success": True, "tray_open": True}

    def close_tray(self) -> dict[str, Any]:
        """Close the plate-reader tray.

        Returns:
            A JSON-safe result containing ``success`` and ``tray_open``.
        """
        with self._command_lock:
            self._submit(self._close_tray())
        return {"success": True, "tray_open": False}

    def read_absorbance(
        self,
        wavelength: int,
        wells: list[str] | None = None,
    ) -> dict[str, Any]:
        """Read absorbance at 230-1000 nm.

        Args:
            wavelength: Measurement wavelength in nanometres.
            wells: Optional well names such as ``["A1", "A2", "B1"]``.
                Omit to read every well.

        Returns:
            A JSON-safe dictionary containing the measurement data.
        """
        wavelength = int(wavelength)
        if not 230 <= wavelength <= 1_000:
            raise ValueError("wavelength must be between 230 and 1000 nm")
        return self._measure(
            "absorbance",
            wavelength=wavelength,
            wells=self._normalize_well_names(wells),
        )

    def read_fluorescence(
        self,
        excitation_wavelength: int,
        emission_wavelength: int,
        focal_height: float = 20.0,
        wells: list[str] | None = None,
    ) -> dict[str, Any]:
        """Read fluorescence from the top of the plate.

        Args:
            excitation_wavelength: Excitation wavelength in nanometres (230-850).
            emission_wavelength: Emission wavelength in nanometres (230-850).
            focal_height: Focal height in millimetres.
            wells: Optional well names. Omit to read every well.

        Returns:
            A JSON-safe dictionary containing the measurement data.
        """
        excitation_wavelength = int(excitation_wavelength)
        emission_wavelength = int(emission_wavelength)
        focal_height = float(focal_height)
        if not 230 <= excitation_wavelength <= 850:
            raise ValueError("excitation_wavelength must be between 230 and 850 nm")
        if not 230 <= emission_wavelength <= 850:
            raise ValueError("emission_wavelength must be between 230 and 850 nm")
        if focal_height < 0:
            raise ValueError("focal_height must be non-negative")
        return self._measure(
            "fluorescence",
            excitation_wavelength=excitation_wavelength,
            emission_wavelength=emission_wavelength,
            focal_height=focal_height,
            wells=self._normalize_well_names(wells),
        )

    def read_luminescence(
        self,
        focal_height: float = 20.0,
        wells: list[str] | None = None,
    ) -> dict[str, Any]:
        """Read luminescence from the selected wells.

        Args:
            focal_height: Focal height in millimetres.
            wells: Optional well names. Omit to read every well.

        Returns:
            A JSON-safe dictionary containing the measurement data.
        """
        focal_height = float(focal_height)
        if focal_height < 0:
            raise ValueError("focal_height must be non-negative")
        return self._measure(
            "luminescence",
            focal_height=focal_height,
            wells=self._normalize_well_names(wells),
        )

    def get_state(self) -> dict[str, Any]:
        """Return the reader's connection and tray state.

        Returns:
            JSON-safe state information for PUDA telemetry.
        """
        with self._state_lock:
            return {
                "state": self._state,
                "connected": self._state not in {"starting", "offline", "stopped"},
                "tray_open": self._tray_open,
                "plate_model": self._plate_model,
                "last_error": self._last_error,
            }

    def get_position(self) -> dict[str, Any]:
        """Return tray position in the standard PUDA position payload.

        Returns:
            A dictionary describing the tray rather than nonexistent XYZ axes.
        """
        with self._state_lock:
            return {"tray": "open" if self._tray_open else "closed"}

    def _measure(self, mode: str, **parameters: Any) -> dict[str, Any]:
        well_names = parameters["wells"]
        with self._command_lock:
            data = self._submit(self._read(mode, parameters))
        return {
            "success": True,
            "mode": mode,
            "plate_model": self._plate_model,
            "wells": well_names,
            "data": self._jsonify(data),
        }

    async def _setup(self) -> None:
        self._set_state("starting")
        try:
            plate_factory = getattr(resources, self._plate_model, None)
            if plate_factory is None or not callable(plate_factory):
                raise ValueError(
                    f"Unknown PyLabRobot plate model {self._plate_model!r}"
                )
            plate = plate_factory(name="plate")
            if not isinstance(plate, Plate):
                raise ValueError(f"{self._plate_model!r} does not create a Plate")

            backend = ExperimentalTecanInfinite200ProBackend(
                counts_per_mm_x=self._counts_per_mm[0],
                counts_per_mm_y=self._counts_per_mm[1],
                counts_per_mm_z=self._counts_per_mm[2],
            )
            reader = PlateReader(
                name="tecan_infinite_200_pro",
                size_x=0,
                size_y=0,
                size_z=0,
                backend=backend,
            )
            reader.assign_child_resource(plate)
            await reader.setup()
            self._reader = reader
            self._plate = plate
            with self._state_lock:
                self._tray_open = False
            self._set_state("idle")
            logger.info(
                "Tecan Infinite 200 PRO initialized over PyUSB (VID=0C47 PID=8007) with %s",
                self._plate_model,
            )
        except Exception as exc:
            self._set_error(exc)
            raise

    async def _shutdown(self) -> None:
        self._set_state("stopping")
        try:
            if self._reader is not None:
                await self._reader.stop()
            self._set_state("stopped")
        except Exception as exc:
            self._set_error(exc)
            raise

    async def _reset(self) -> None:
        reader = self._require_reader()
        self._set_state("resetting")
        try:
            await reader.stop()
            await reader.setup()
            with self._state_lock:
                self._tray_open = False
            self._set_state("idle")
        except Exception as exc:
            self._set_error(exc)
            raise

    async def _open_tray(self) -> None:
        reader = self._require_reader()
        self._set_state("moving")
        try:
            await reader.open()
            with self._state_lock:
                self._tray_open = True
            self._set_state("idle")
        except Exception as exc:
            self._set_error(exc)
            raise

    async def _close_tray(self) -> None:
        reader = self._require_reader()
        self._set_state("moving")
        try:
            await reader.close()
            with self._state_lock:
                self._tray_open = False
            self._set_state("idle")
        except Exception as exc:
            self._set_error(exc)
            raise

    async def _read(self, mode: str, parameters: dict[str, Any]) -> Any:
        reader = self._require_reader()
        plate = self._require_plate()
        well_names = parameters.pop("wells")
        kwargs = dict(parameters)
        if well_names is not None:
            kwargs["wells"] = plate.get_items(well_names)

        self._set_state("reading")
        try:
            if mode == "absorbance":
                result = await reader.read_absorbance(**kwargs)
            elif mode == "fluorescence":
                result = await reader.read_fluorescence(**kwargs)
            elif mode == "luminescence":
                result = await reader.read_luminescence(**kwargs)
            else:
                raise ValueError(f"Unsupported measurement mode: {mode}")
            self._set_state("idle")
            return result
        except Exception as exc:
            self._set_error(exc)
            raise

    def _run_event_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
        pending = asyncio.all_tasks(self._loop)
        for task in pending:
            task.cancel()
        if pending:
            self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        self._loop.close()

    def _submit(self, coroutine: Coroutine[Any, Any, Any]) -> Any:
        if not self._loop_thread.is_alive():
            coroutine.close()
            raise RuntimeError("Tecan driver event loop is not running")
        future: Future[Any] = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        return future.result(timeout=self._command_timeout)

    def _stop_event_loop(self) -> None:
        if self._loop_thread.is_alive():
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._loop_thread.join(timeout=5)

    def _require_reader(self) -> PlateReader:
        if self._reader is None:
            raise RuntimeError("Tecan reader is not initialized")
        return self._reader

    def _require_plate(self) -> Plate:
        if self._plate is None:
            raise RuntimeError("Plate model is not initialized")
        return self._plate

    @staticmethod
    def _normalize_well_names(wells: list[str] | None) -> list[str] | None:
        if wells is None:
            return None
        if not isinstance(wells, list) or not wells:
            raise ValueError("wells must be a non-empty list of well names or null")
        normalized = [str(well).strip().upper() for well in wells]
        if any(not well for well in normalized):
            raise ValueError("well names must not be empty")
        return normalized

    def _set_state(self, state: str) -> None:
        with self._state_lock:
            self._state = state
            self._last_error = None

    def _set_error(self, exc: Exception) -> None:
        with self._state_lock:
            self._state = "offline"
            self._last_error = str(exc)
        logger.exception("Tecan Infinite 200 PRO operation failed")

    @staticmethod
    def _jsonify(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {
                str(key): Tecan_Infinite_200_pro._jsonify(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [Tecan_Infinite_200_pro._jsonify(item) for item in value]
        if hasattr(value, "tolist"):
            return Tecan_Infinite_200_pro._jsonify(value.tolist())
        return str(value)
