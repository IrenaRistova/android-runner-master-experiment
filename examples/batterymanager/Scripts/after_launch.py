# noinspection PyUnusedLocal,PyUnusedLocal
def main(device, *args, **kwargs):
    # Debugging aid: shows what Android Runner passes in for this hook.
    print("AFTER_LAUNCH ARGS:", args)
    print("AFTER_LAUNCH KWARGS:", kwargs)

    # NOTE: We intentionally do NOT start Monkey from this hook.
    # On NativeExperiment runs, Android Runner doesn't pass the subject package here,
    # and device.current_activity() can point to the BatteryManager utility screen.
    # Monkey is started from Scripts/interaction.py where we can access experiment.package.
