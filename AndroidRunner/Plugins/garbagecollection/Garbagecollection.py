import os.path as op
import os
import time
import csv

from AndroidRunner.Plugins.Profiler import Profiler


class ConfigError(Exception):
    pass


class Garbagecollection(Profiler):
    def __init__(self, config, paths):
        super(Garbagecollection, self).__init__(config, paths)
        self.output_dir = ''
        self.logcat_output = ''
        self.profile = False

    def start_profiling(self, device, **kwargs):
        self.profile = True
        self.logcat_output = '{}logcat_{}_{}.txt'.format(self.output_dir, device.id, time.strftime('%Y.%m.%d_%H%M%S'))

    def stop_profiling(self, device, **kwargs):
        self.profile = False

    def collect_results(self, device, path=None):
        # Patched 2026-06-30:
        # Bug 1: /mnt/sdcard/ is blocked by scoped storage on Android 13+ —
        #   logcat -f returns 'Permission denied', the pull silently grabs
        #   nothing, GC count comes out 0. Fix: write to /data/local/tmp/
        #   which is accessible to the adb shell user on every Pixel tested
        #   (P3 Android 12, P6 + P9 Android 16).
        # Bug 2: 'AllocSpace objects,' check no longer matches — modern
        #   Android logs "GC freed 320KB AllocSpace bytes, 0(0B) LOS objects"
        #   ('bytes', not 'objects', for AllocSpace). Simplify to just
        #   'GC freed'.
        device_path = '/data/local/tmp/ar_gc_logcat.txt'
        device.shell('logcat -f {} -d'.format(device_path))

        pull_result = device.pull(device_path, self.logcat_output)
        if pull_result is None or 'error' in pull_result.decode():
            self.logger.critical(
                'Failed to pull logcat from {} — cannot gather GC calls.'.format(device_path)
            )
            return

        device.shell('rm -f {}'.format(device_path))

        collections_filename = 'collections_{}_{}.csv'.format(device.id, time.strftime('%Y.%m.%d_%H%M%S'))
        total_filename = 'total_{}_{}.csv'.format(device.id, time.strftime('%Y.%m.%d_%H%M%S'))
        collections_count = 0

        with open(self.logcat_output) as logcat:
            with open(op.join(self.output_dir, collections_filename), 'w+') as output:
                lines = logcat.readlines()
                for i, line in enumerate(lines):
                    if 'GC freed' in line:
                        output.write(line)
                        collections_count += 1
        with open(op.join(self.output_dir, total_filename), 'a') as output:
            writer = csv.writer(output)
            writer.writerow(['garbage_collection_count'])
            writer.writerow([collections_count])
        os.remove(self.logcat_output)

    def set_output(self, output_dir):
        self.output_dir = output_dir

    def dependencies(self):
        return []

    def load(self, device):
        return

    def unload(self, device):
        return

    def aggregate_subject(self):
        # Patched 2026-06-30 -- was writing 'delayed_frames' as the header
        # (copy-paste from the frametimes plugin), making the GC aggregator's
        # output unparseable.
        with open(op.join(self.output_dir, 'all_garbage_collection_counts.csv'), 'w+') as output:
            writer = csv.writer(output)
            writer.writerow(['garbage_collection_count'])
            for output_file in os.listdir(self.output_dir):
                if output_file.startswith("total"):
                    writer.writerow([int(open(op.join(self.output_dir, output_file)).readlines()[1])])

    def aggregate_end(self, data_dir, output_file):
        return

    def aggregate_final(self, data_dir):
        return
