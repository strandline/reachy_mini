"""Unit tests for the GPIO23 shutdown-button monitor.

Regression coverage for issue #1109: motor-coil EMI on GPIO23 must not fire
``shutdown_now`` (transient-burst test) while a deliberate sustained press
still must (long-hold test).

Drives ``gpiozero`` via its ``MockFactory`` so the tests run on any host —
no real GPIO required. The tests use a small ``hold_time`` (0.3 s) so the
suite stays fast; the production constant ``HOLD_TIME = 2.0`` is verified
separately by ``test_module_constants_match_design``.
"""

import time
from unittest.mock import patch

import pytest

# gpiozero is a Linux-only optional dep in pyproject.toml; on macOS / Windows
# the wheel may be installable but pin operations require a backend. We skip
# this module if gpiozero is unimportable rather than failing the suite.
gpiozero = pytest.importorskip("gpiozero")
from gpiozero import Device  # noqa: E402
from gpiozero.pins.mock import MockFactory  # noqa: E402

from reachy_mini.daemon.app.services.gpio_shutdown.shutdown_monitor import (  # noqa: E402
    HOLD_TIME,
    install_handler,
    shutdown_now,
)


@pytest.fixture
def mock_factory():
    """Swap in a ``MockFactory`` for the duration of the test."""
    previous = Device.pin_factory
    Device.pin_factory = MockFactory()
    try:
        yield Device.pin_factory
    finally:
        # gpiozero.Device.close() implicitly cleans pins; resetting the
        # factory after each test isolates state between tests.
        Device.pin_factory.reset()
        Device.pin_factory = previous


def test_module_constants_match_design():
    """Production HOLD_TIME stays at 2.0 s (#1109 acceptance criterion)."""
    assert HOLD_TIME == 2.0


def test_transient_noise_does_not_trigger_when_held(mock_factory):
    """EMI bursts shorter than ``hold_time`` must NOT fire ``when_held``.

    Simulates the #1109 failure mode — short, repeated active pulses on
    GPIO23. Each pulse is well under ``hold_time``; ``when_held`` should
    never fire.
    """
    fired: list[bool] = []
    button = install_handler(pin=23, hold_time=0.3)
    # Re-bind so we observe firing without invoking the real subprocess.
    button.when_held = lambda: fired.append(True)
    pin = mock_factory.pin(23)

    for _ in range(5):
        pin.drive_high()       # transient burst — pin floats high
        time.sleep(0.1)        # 0.1 s << 0.3 s hold_time
        pin.drive_low()        # released
        time.sleep(0.05)

    # Poll past one hold_time; bail out early if late firing is observed so
    # the assertion message points at the offending burst rather than a
    # generic timeout.
    deadline = time.monotonic() + 0.4
    while time.monotonic() < deadline:
        if fired:
            break
        time.sleep(0.01)

    assert fired == [], (
        f"hold_time=0.3s did not suppress 0.1s transient bursts: fired={fired}"
    )


def test_sustained_press_triggers_when_held(mock_factory):
    """A continuous press > ``hold_time`` MUST fire ``when_held`` exactly once."""
    fired: list[bool] = []
    button = install_handler(pin=23, hold_time=0.3)
    button.when_held = lambda: fired.append(True)
    pin = mock_factory.pin(23)

    pin.drive_high()
    time.sleep(0.5)            # 0.5 s > 0.3 s hold_time
    pin.drive_low()
    time.sleep(0.05)

    assert fired == [True], f"Sustained press did not fire when_held: fired={fired}"


def test_shutdown_now_invokes_shutdown_command():
    """``shutdown_now`` must call ``sudo shutdown -h now`` exactly once."""
    target = "reachy_mini.daemon.app.services.gpio_shutdown.shutdown_monitor.call"
    with patch(target) as mock_call:
        shutdown_now()
    mock_call.assert_called_once_with(["sudo", "shutdown", "-h", "now"])
