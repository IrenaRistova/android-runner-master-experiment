"""``before_run`` hook for the BatteryManager experiments.

In addition to the original ``am start`` of the BatteryManager utility, this
hook now produces ``apk_meta.json`` for the active run so the
``after_experiment`` tracking-matrix updater can populate the
``apk_path`` / ``apk_sha256`` / ``apk_storage`` columns without needing
those values to be passed on the CLI.

Implementation note: AndroidRunner's ``scripts.before_run`` slot accepts a
single script path, so we extend this existing hook rather than wiring a
new one into every experiment JSON. The chain-on-existing-hook pattern is
the same one ``after_run.py`` already uses for ``detect_crash_anr``.
"""

import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def _resolve_run_output_dir():
    """Best-effort resolution of the directory ``apk_meta.json`` should land in.

    Prefers ``paths.OUTPUT_DIR`` (per-(device, subject) data folder) because
    ``update_tracking_matrix.py:_find_apk_meta`` matches that location via
    its ``data/*/*/apk_meta.json`` glob. Falls back to ``BASE_OUTPUT_DIR``.
    """
    try:
        import paths as ar_paths  # type: ignore
    except Exception:
        return None
    out = getattr(ar_paths, "OUTPUT_DIR", None)
    if out and os.path.isdir(out):
        return out
    base = getattr(ar_paths, "BASE_OUTPUT_DIR", None)
    if base and os.path.isdir(base):
        return base
    return None


def _resolve_apk_path(args, kwargs):
    """Pull the active APK path out of whatever AndroidRunner forwarded.

    AndroidRunner calls ``scripts.run('before_run', device, *args, **kwargs)``
    where ``kwargs['current_run']`` is a dict containing ``path`` -- the APK
    path for this run (see ``AndroidRunner/Experiment.py``). Some callers
    may pass the path as a positional, so we accept both.
    """
    current_run = kwargs.get("current_run") if isinstance(kwargs, dict) else None
    if isinstance(current_run, dict):
        path = current_run.get("path")
        if path:
            return path
    for arg in args or ():
        if isinstance(arg, str) and arg.lower().endswith(".apk"):
            return arg
    return None


# noinspection PyUnusedLocal
def main(device, *args, **kwargs):
    device.shell('am start -n "com.example.batterymanager_utility/com.example.batterymanager_utility.MainActivity" -a android.intent.action.MAIN -c android.intent.category.LAUNCHER')
    time.sleep(5)

    try:
        import _lib_apk_meta
        run_output_dir = _resolve_run_output_dir()
        apk_path = _resolve_apk_path(args, kwargs)
        _lib_apk_meta.write_apk_meta(run_output_dir, apk_path)
    except Exception as exc:  # noqa: BLE001 - hook must never crash the experiment
        try:
            sys.stderr.write(
                "before_run: apk_meta hook failed (continuing): {}: {}\n".format(
                    type(exc).__name__, exc
                )
            )
        except Exception:
            pass

    # E0.T8 — per-run device_state.json snapshot. Captures battery /
    # discharge / brightness / airplane-mode / etc. so the matrix updater
    # can tag rows with `energy_invalid_usb_supplying` when the
    # charge controller flipped between runs (noise sources § 1b
    # "float-charge masking"). Never raises; failure logs to stderr and the
    # row simply loses its discharge tag.
    try:
        import before_run_record_device_state as _device_state_recorder
        _device_state_recorder.record_device_state(device, _resolve_run_output_dir())
    except Exception as exc:  # noqa: BLE001 - hook must never crash the experiment
        try:
            sys.stderr.write(
                "before_run: device_state.json hook failed (continuing): {}: {}\n".format(
                    type(exc).__name__, exc
                )
            )
        except Exception:
            pass

    # E1.5.T1 + T2: CPU + memory sampling is performed by Android Runner's
    # built-in `android` profiler plugin (Plugins/android/Android.py); see the
    # `profilers.android` block in the experiment JSON. No before_run wiring
    # required — the profiler lifecycle is driven by AndroidRunner itself.
    # E1.5.T3: per-run logcat capture is provided by the BatteryManager
    # plugin's `adb_log` persistency_strategy (already enabled in every
    # active config); the resulting `logcat_<serial>_<ts>.txt` is consumed
    # automatically by `detect_crash_anr.read_logcat_from_run_dir`.
