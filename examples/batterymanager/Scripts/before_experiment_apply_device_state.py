"""``before_experiment`` helper: apply device-state controls + discharge-validity check.

Sibling helper to ``before_experiment_grant_battery_stats.py``; invoked from
``before_experiment_uninstall_metronome.py`` (and the catch-all
``before_experiment.py``) via the chain-on-existing-hook pattern.

What this hook does on every experiment start:

  1. **Brightness lock** (noise source § 2): force adaptive brightness OFF
     and pin ``screen_brightness=128`` so day-vs-night ambient drift cannot
     leak ~200 mW of differential into the energy reading.

  2. **Best-effort software charge-disable** (noise source § 1, § 5):
     run the standard ``dumpsys battery unplug`` + ``set ac/usb/wireless 0``
     + ``set status 3`` sequence. On Pixel 3 / Pixel 9 this is known to be
     accepted by the Android API but ignored by the charging IC; we still
     run it so a per-device cache file documents "we tried" and so devices
     where the API *does* work get the right behaviour for free.

  3. **Discharge-validity ground-truth** (noise source § 1b): wait 5 s then
     read ``/sys/class/power_supply/battery/current_now``. Negative =
     verified discharge (battery is the source); non-negative = the charge
     IC is still supplying / dominating, the energy reading on this run
     will be USB-masked.

  4. **Per-device capability cache**: write a small JSON to
     ``Scripts/.device_state_capabilities/<serial>.json`` recording
     whether software charge-disable actually worked on this device. The
     matrix updater can later cite this as the explanation for why a row
     is tagged ``energy_invalid_usb_supplying``.

Strict-mode behaviour (``MASTEREXP_STRICT_DISCHARGE_CHECK=1``):
    Default lenient mode (env var unset) → log a warning and continue.
    Strict mode (env var = ``"1"``) → write a sentinel file and call
    ``sys.exit(1)``. Use strict mode for the eventual thesis batch where
    a USB-supplied row would silently corrupt the comparison.

Out of scope (per E0.T8):
    - Do NOT automate airplane mode.
    - Do NOT modify the BatteryManager plugin.
    - Do NOT install / configure ``hub-ctrl`` (that is Epic 1.6).
"""

from __future__ import annotations

import os
import os.path as op
import sys
from typing import Any, Dict, Optional

_HERE = op.dirname(op.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def _log_stdout(msg: str) -> None:
    try:
        sys.stdout.write(msg + "\n")
        sys.stdout.flush()
    except Exception:
        pass


def _log_stderr(msg: str) -> None:
    try:
        sys.stderr.write(msg + "\n")
        sys.stderr.flush()
    except Exception:
        pass


def _resolve_experiment_root() -> Optional[str]:
    """Best-effort: where to drop the strict-mode sentinel file.

    ``paths.BASE_OUTPUT_DIR`` (top-level run dir) is the most useful target
    because the operator inspects it after a failed experiment. Falls back
    to ``OUTPUT_DIR`` (per-subject) and finally to the Scripts directory.
    """
    try:
        import paths as ar_paths  # type: ignore
    except Exception:
        return None
    base = getattr(ar_paths, "BASE_OUTPUT_DIR", None)
    if base and op.isdir(base):
        return base
    out = getattr(ar_paths, "OUTPUT_DIR", None)
    if out and op.isdir(out):
        return out
    return None


def _write_strict_failure_sentinel(snapshot: Dict[str, Any]) -> Optional[str]:
    """In strict mode, drop a JSON sentinel describing the discharge failure."""
    try:
        import json
        target_dir = _resolve_experiment_root() or _HERE
        path = op.join(target_dir, "device_state_strict_check_failed.json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, sort_keys=True, default=str)
            f.write("\n")
        os.replace(tmp, path)
        return path
    except Exception as ex:
        _log_stderr(
            "before_experiment_apply_device_state: failed to write strict sentinel: %s: %s"
            % (type(ex).__name__, ex)
        )
        return None


def apply_device_state(device) -> Dict[str, Any]:
    """Apply brightness + charge-disable + verify discharge; cache capabilities.

    Returns the assembled snapshot dict (same schema as ``device_state.json``)
    for callers that want to log or assert on it. The function is independent
    of the per-run hook (which builds its own fresh snapshot) — this one runs
    once per experiment and is the place where state-changing actions happen.

    Raises ``SystemExit(1)`` only when:
      - ``MASTEREXP_STRICT_DISCHARGE_CHECK=1`` is set in the environment, AND
      - the post-settle ``current_now`` reading does not classify as
        ``verified_discharge``.

    In every other case the function returns normally — failures are logged
    to stderr and surface as ``"unknown"`` / ``None`` fields in the snapshot.
    """
    import _lib_device_state as ds

    serial = ds.get_device_serial(device)
    _log_stdout(
        "before_experiment_apply_device_state: starting on %s "
        "(strict_mode=%s)" % (serial, "ON" if ds.strict_mode_enabled() else "OFF")
    )

    brightness_result: Optional[Dict[str, Any]] = None
    try:
        brightness_result = ds.apply_brightness_lock(device)
    except Exception as ex:
        _log_stderr(
            "before_experiment_apply_device_state: brightness lock raised on %s "
            "(continuing): %s: %s" % (serial, type(ex).__name__, ex)
        )

    disable_result: Optional[Dict[str, Any]] = None
    try:
        disable_result = ds.attempt_disable_charging(device)
    except Exception as ex:
        _log_stderr(
            "before_experiment_apply_device_state: attempt_disable_charging raised on %s "
            "(continuing): %s: %s" % (serial, type(ex).__name__, ex)
        )

    snapshot = ds.assemble_device_state_snapshot(device)

    cache_payload = {
        "device_serial": serial,
        "android_release": snapshot.get("android_release"),
        "cpu_abilist": snapshot.get("cpu_abilist"),
        "last_attempt_disable_charging": disable_result,
        "last_brightness_lock": brightness_result,
        "last_discharge_verdict": snapshot.get("discharge_verdict"),
        "last_current_now_raw": snapshot.get("current_now_raw"),
        "last_observed_at": snapshot.get("captured_at"),
        "last_battery_level_pct": snapshot.get("battery_level_pct"),
    }
    written = ds.write_capability_cache(serial, cache_payload)
    if written:
        _log_stdout(
            "before_experiment_apply_device_state: cached capability record at %s" % written
        )

    verdict = snapshot.get("discharge_verdict") or "unknown"
    current_raw = snapshot.get("current_now_raw")
    if verdict == "verified_discharge":
        _log_stdout(
            "before_experiment_apply_device_state: discharge verified on %s "
            "(current_now=%s) — energy reading on this experiment is trustworthy"
            % (serial, current_raw)
        )
    elif verdict == "suspected_supplying":
        _log_stderr(
            "before_experiment_apply_device_state: discharge NOT verified on %s "
            "(current_now=%s ≥ 0). USB / charge-IC is still supplying. Per-row "
            "energy values WILL be USB-masked. Mitigation: hub-ctrl (Epic 1.6) "
            "or wireless ADB (RUNBOOK §5)." % (serial, current_raw)
        )
    else:
        _log_stderr(
            "before_experiment_apply_device_state: discharge UNKNOWN on %s "
            "(current_now unreadable). Treating as suspected_supplying for "
            "downstream tagging." % serial
        )

    if ds.strict_mode_enabled() and verdict != "verified_discharge":
        sentinel_path = _write_strict_failure_sentinel(snapshot)
        _log_stderr(
            "before_experiment_apply_device_state: STRICT MODE ACTIVE and "
            "discharge_verdict=%r on %s — aborting experiment. Sentinel: %s. "
            "To proceed anyway: unset %s in your shell."
            % (
                verdict,
                serial,
                sentinel_path or "<not written>",
                "MASTEREXP_STRICT_DISCHARGE_CHECK",
            )
        )
        sys.exit(1)

    return snapshot


def main(device, *args, **kwargs):
    """Module entrypoint for direct AndroidRunner ``before_experiment`` wiring.

    The catch-all ``before_experiment.py`` and the per-app
    ``before_experiment_uninstall_metronome.py`` import this module and call
    ``apply_device_state`` directly (chain-on-existing-hook pattern). This
    ``main`` exists for symmetry / smoke-testing.
    """
    try:
        apply_device_state(device)
    except SystemExit:
        raise
    except Exception as ex:
        _log_stderr(
            "before_experiment_apply_device_state.main: unexpected exception "
            "(swallowed; experiment continues): %s: %s"
            % (type(ex).__name__, ex)
        )
