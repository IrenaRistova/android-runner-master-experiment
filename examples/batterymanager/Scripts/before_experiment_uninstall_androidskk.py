"""before_experiment for AndroidSKK."""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path: sys.path.insert(0, _HERE)
PACKAGE = "jp.deadend.noname.skk"

def main(device, *args, **kwargs):
    try:
        import before_experiment_apply_device_state as _ds; _ds.apply_device_state(device)
    except SystemExit: raise
    except Exception as exc:
        try: sys.stderr.write("device_state failed: %s: %s\n" % (type(exc).__name__, exc))
        except Exception: pass
    try:
        import before_experiment_grant_battery_stats as _g; _g.grant_battery_stats(device)
    except Exception as exc:
        try: sys.stderr.write("grant failed: %s: %s\n" % (type(exc).__name__, exc))
        except Exception: pass
    try:
        if PACKAGE not in device.get_app_list():
            device.logger.info("%s not installed.", PACKAGE); return
        device.uninstall(PACKAGE)
    except Exception as exc:
        try: sys.stderr.write("uninstall failed: %s: %s\n" % (type(exc).__name__, exc))
        except Exception: pass
