import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


# noinspection PyUnusedLocal
def main(device, *args, **kwargs):
    device.shell('am force-stop com.example.batterymanager_utility')

    try:
        import detect_crash_anr
        detect_crash_anr.main(device, *args, **kwargs)
    except Exception as exc:
        try:
            sys.stderr.write(
                "after_run: detect_crash_anr hook failed (continuing): {}: {}\n".format(
                    type(exc).__name__, exc
                )
            )
        except Exception:
            pass

    # E1.5.T5 — `aux_postprocess` USED to be chained here, but the built-in
    # `android` profiler's CSV is only written during `aggregate_subject`,
    # which fires AFTER `after_run` returns (empirically ~12 s later in the
    # 2026-05-08T19:30 run). Calling the post-processor here read no CSV and
    # wrote no aux_summary.json. Moved to `after_experiment.py` where every
    # per-subject CSV is on disk by the time we walk the data tree.
