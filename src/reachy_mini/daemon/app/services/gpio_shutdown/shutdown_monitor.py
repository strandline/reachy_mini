"""Monitor GPIO23 for the body shutdown-button signal.

Hardware: GPIO23 is wired to the body button. ``pull_up=False`` keeps gpiozero
from overriding the kernel-side pull configured in the device tree.

Issue #1109: under sustained motor activity (e.g. 10 Hz ``set_target`` calls
during TTS lip-sync) the previous busy-wait debounce introduced in PR #505 is
insufficient — motor-coil EMI couples into the GPIO23 input long enough to
exceed the 200 ms debounce window and fire spurious shutdowns. This module
now uses gpiozero's native ``hold_time`` / ``when_held`` mechanism, which
fires only after ``HOLD_TIME`` seconds of *continuous* press. Transient EMI
bursts no longer satisfy the continuity check, while a deliberate user press
of >= 2 s still triggers shutdown.
"""

from signal import pause
from subprocess import call

from gpiozero import Button

#: Sustained-press duration (seconds) before the shutdown handler fires.
#: Longer than any motor-EMI burst observed in #1109; still a natural gesture.
HOLD_TIME: float = 2.0


def shutdown_now() -> None:
    """Issue ``sudo shutdown -h now``. Bound to ``Button.when_held``."""
    print("Shutdown button held, shutting down...")
    call(["sudo", "shutdown", "-h", "now"])


def install_handler(pin: int = 23, hold_time: float = HOLD_TIME) -> Button:
    """Construct the ``Button`` and bind ``when_held`` to ``shutdown_now``.

    Returned for tests; production caller in ``main()`` discards it.
    """
    button = Button(pin, pull_up=False, hold_time=hold_time)
    button.when_held = shutdown_now
    return button


def main() -> None:
    """Entry point. Bind the handler and block on ``signal.pause()``."""
    install_handler()
    print(f"Monitoring GPIO23 for {HOLD_TIME}s sustained press...")
    pause()


if __name__ == "__main__":
    main()
