# noinspection PyUnusedLocal
"""``before_experiment`` hook for CRcontainer. See ``before_experiment_uninstall_metronome.py``."""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

PACKAGE = "org.curiouslearning.container"


def main(device, *args, **kwargs):
    try:
        import before_experiment_apply_device_state as _device_state
        _device_state.apply_device_state(device)
    except SystemExit:
        raise
    except Exception as exc:
        try:
            sys.stderr.write(
                "before_experiment_uninstall_crcontainer: device-state chain failed: %s: %s\n"
                % (type(exc).__name__, exc))
        except Exception:
            pass

    try:
        import before_experiment_grant_battery_stats as _grant
        _grant.grant_battery_stats(device)
    except Exception as exc:
        try:
            sys.stderr.write(
                "before_experiment_uninstall_crcontainer: BATTERY_STATS grant failed: %s: %s\n"
                % (type(exc).__name__, exc))
        except Exception:
            pass

    try:
        if PACKAGE not in device.get_app_list():
            device.logger.info("%s not installed", PACKAGE)
            return
        device.logger.info("Uninstalling %s", PACKAGE)
        device.uninstall(PACKAGE)
    except Exception as exc:
        try:
            sys.stderr.write(
                "before_experiment_uninstall_crcontainer: uninstall failed: %s: %s\n"
                % (type(exc).__name__, exc))
        except Exception:
            pass
