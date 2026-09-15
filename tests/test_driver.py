import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from driver import Tecan_Infinite_200_pro


class DriverConnectionTests(unittest.TestCase):
    def test_setup_uses_pylabrobot_native_usb_backend(self):
        backend = object()
        reader = MagicMock()
        reader.setup = AsyncMock()
        reader.stop = AsyncMock()

        with (
            patch("driver.ExperimentalTecanInfinite200ProBackend", return_value=backend),
            patch("driver.PlateReader", return_value=reader) as reader_class,
        ):
            machine = Tecan_Infinite_200_pro(
                plate_model="cor_96_wellplate_360uL_Fb",
                counts_per_mm_x=1000,
                counts_per_mm_y=1000,
                counts_per_mm_z=1000,
                command_timeout=10,
            )
            try:
                self.assertIs(reader_class.call_args.kwargs["backend"], backend)
                reader.setup.assert_awaited_once()
                self.assertTrue(machine.get_state()["connected"])
            finally:
                machine.shutdown()


if __name__ == "__main__":
    unittest.main()
