from __future__ import annotations

import asyncio
import threading
import unittest

from driver import Tecan_Infinite_200_pro, setup_tecan_reader


class _FakeIO:
    dev = None


class _FakeBackend:
    def __init__(self) -> None:
        self.io = _FakeIO()
        self.recovery_calls = 0

        async def recover_transport() -> None:
            self.recovery_calls += 1

        self.original_recover_transport = recover_transport
        self._recover_transport = recover_transport


class _FakeReader:
    def __init__(self, backend: _FakeBackend) -> None:
        self.backend = backend
        self.stop_calls = 0
        self.setup_calls = 0
        self.recovery_was_deferred = False

    async def stop(self) -> None:
        self.stop_calls += 1

    async def setup(self) -> None:
        self.setup_calls += 1
        self.recovery_was_deferred = (
            self.backend._recover_transport is not self.backend.original_recover_transport
        )
        await self.backend._recover_transport()


class ResetInitializationTests(unittest.TestCase):
    def test_reset_defers_transport_recovery_during_setup(self) -> None:
        backend = _FakeBackend()
        reader = _FakeReader(backend)
        driver = Tecan_Infinite_200_pro.__new__(Tecan_Infinite_200_pro)
        driver._reader = reader
        driver._backend = backend
        driver._state_lock = threading.RLock()
        driver._state = "idle"
        driver._last_error = None
        driver._tray_open = True

        with self.assertLogs("driver", level="WARNING") as captured:
            asyncio.run(driver._reset())

        self.assertEqual(reader.stop_calls, 1)
        self.assertEqual(reader.setup_calls, 1)
        self.assertTrue(reader.recovery_was_deferred)
        self.assertEqual(backend.recovery_calls, 0)
        self.assertIs(
            backend._recover_transport,
            backend.original_recover_transport,
            "normal transport recovery must be restored after reset setup",
        )
        self.assertEqual(driver._state, "idle")
        self.assertFalse(driver._tray_open)
        self.assertTrue(
            any("deferring transport recovery" in message for message in captured.output)
        )


class _ConnectedFakeIO:
    def __init__(self) -> None:
        self.dev = object()
        self.stop_calls = 0

    async def stop(self) -> None:
        self.stop_calls += 1
        self.dev = None


class _CleanupFailingFakeIO(_ConnectedFakeIO):
    async def stop(self) -> None:
        self.stop_calls += 1
        raise OSError("cleanup failed")


class _FailingReader:
    async def setup(self) -> None:
        raise RuntimeError("handshake failed")


class _SuccessfulReader:
    async def setup(self) -> None:
        return None


class SetupFailureTests(unittest.TestCase):
    def test_setup_logs_original_failure_before_usb_cleanup(self) -> None:
        backend = _FakeBackend()
        backend.io = _ConnectedFakeIO()

        with self.assertLogs("driver", level="ERROR") as captured:
            with self.assertRaisesRegex(RuntimeError, "handshake failed"):
                asyncio.run(setup_tecan_reader(_FailingReader(), backend))

        self.assertEqual(backend.io.stop_calls, 1)
        self.assertIs(
            backend._recover_transport,
            backend.original_recover_transport,
            "normal transport recovery must be restored after setup failure",
        )
        self.assertTrue(
            any(
                "Tecan initialization failed; releasing partial USB connection"
                in message
                for message in captured.output
            ),
            captured.output,
        )

    def test_cleanup_failure_does_not_hide_initialization_failure(self) -> None:
        backend = _FakeBackend()
        backend.io = _CleanupFailingFakeIO()

        with self.assertLogs("driver", level="ERROR") as captured:
            with self.assertRaisesRegex(RuntimeError, "handshake failed"):
                asyncio.run(setup_tecan_reader(_FailingReader(), backend))

        messages = "\n".join(captured.output)
        self.assertIn("Failed to release partial Tecan USB connection", messages)
        self.assertIs(
            backend._recover_transport,
            backend.original_recover_transport,
            "normal transport recovery must be restored after cleanup failure",
        )


class SetupLifecycleLoggingTests(unittest.TestCase):
    def test_initial_setup_defers_transport_recovery(self) -> None:
        backend = _FakeBackend()
        reader = _FakeReader(backend)

        with self.assertLogs("driver", level="WARNING") as captured:
            asyncio.run(setup_tecan_reader(reader, backend))

        self.assertTrue(reader.recovery_was_deferred)
        self.assertEqual(backend.recovery_calls, 0)
        self.assertIs(
            backend._recover_transport,
            backend.original_recover_transport,
        )
        self.assertTrue(
            any("deferring transport recovery" in message for message in captured.output)
        )

    def test_setup_logs_start_and_completion_phases(self) -> None:
        backend = _FakeBackend()

        with self.assertLogs("driver", level="INFO") as captured:
            asyncio.run(setup_tecan_reader(_SuccessfulReader(), backend))

        messages = "\n".join(captured.output)
        self.assertIn("Starting guarded Tecan USB initialization", messages)
        self.assertIn("Guarded Tecan USB initialization completed", messages)


if __name__ == "__main__":
    unittest.main()
