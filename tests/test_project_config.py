from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ProjectDependencyTests(unittest.TestCase):
    def test_pylabrobot_is_pinned_to_verified_version(self) -> None:
        with (PROJECT_ROOT / "pyproject.toml").open("rb") as config_file:
            project = tomllib.load(config_file)["project"]

        pylabrobot_dependencies = [
            dependency
            for dependency in project["dependencies"]
            if dependency.startswith("pylabrobot")
        ]

        self.assertEqual(pylabrobot_dependencies, ["pylabrobot[usb]==0.2.2"])

        with (PROJECT_ROOT / "uv.lock").open("rb") as lock_file:
            packages = tomllib.load(lock_file)["package"]

        project_package = next(
            package
            for package in packages
            if package["name"] == "imre-tecan-infinite-200-pro-edge"
        )
        locked_requirement = next(
            requirement
            for requirement in project_package["metadata"]["requires-dist"]
            if requirement["name"] == "pylabrobot"
        )
        self.assertEqual(locked_requirement["specifier"], "==0.2.2")


if __name__ == "__main__":
    unittest.main()
