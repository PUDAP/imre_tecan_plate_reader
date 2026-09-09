"""
Example driver class for a machine.

All public methods should be documented with a docstring, arguments, and return type.

Methods that are not part of the puda CLI contract (helpers, one-off utilities, anything
the operator should not invoke as a machine command) must be private: define them with a
leading underscore (e.g. ``_poll_status``). Only public names are exposed to puda; private
names stay internal to this driver implementation.

Below are the public methods that are exposed to the puda CLI.

- `shutdown`
- `home`
- `reset`
"""


class Driver:
    """
    Replace this with one sentence describing the machine and its functionality.
    """
    def __init__(self):
        # Initialize config and start the machine
        pass

    def shutdown(self) -> bool:
        """
        Shutdown the machine. Releases all resources and connections to the machine.

        Returns:
            bool: True if the shutdown was successful, False otherwise
        """
        return True

    def home(self) -> bool:
        """
        Homes the machine. Used by PUDA CLI `puda machine home <machine_id>`

        Returns:
            bool: True if the home was successful, False otherwise
        """
        return True

    def reset(self) -> bool:
        """
        Software reset the machine. Used by PUDA CLI `puda machine reset <machine_id>`

        Returns:
            bool: True if the reset was successful, False otherwise
        """
        return True

    def get_position(self):
        """
        Get the current position of the machine (optional - if the machine has a position sensor)

        Returns:
            dict: A dictionary containing the current position of the machine
        """
        return {"x": 0, "y": 0, "z": 0}
