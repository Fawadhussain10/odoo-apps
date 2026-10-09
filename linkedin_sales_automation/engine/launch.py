#!/usr/bin/env python3
"""Start one LinkedIn engine detached from Odoo and print its pid.

Odoo runs this small script and waits for it; it starts the engine in a new
session (its own process group, no controlling terminal) and exits at once.
The engine is then a child of init, so it survives the recycling of Odoo
workers and never stays behind as a zombie of one.

    launch.py --cwd DIR --log FILE -- command ...
"""
import argparse
import os
import resource
import subprocess
import sys

MAX_LOG_BYTES = 5 * 1024 * 1024
# Odoo lowers the soft limits of its own processes (limit_memory_hard sets the
# address space, limit_time_cpu the CPU time) and children inherit them. A
# browser reserves far more address space than it uses, and the engine runs for
# days: give it back the system limits.
INHERITED_LIMITS = ('RLIMIT_AS', 'RLIMIT_DATA', 'RLIMIT_CPU', 'RLIMIT_RSS')


def lift_inherited_limits():
    for name in INHERITED_LIMITS:
        limit = getattr(resource, name, None)
        if limit is None:
            continue
        try:
            _soft, hard = resource.getrlimit(limit)
            resource.setrlimit(limit, (hard, hard))
        except (ValueError, OSError):
            pass


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if '--' not in argv:
        print('usage: launch.py --cwd DIR --log FILE -- command ...', file=sys.stderr)
        return 64
    split = argv.index('--')
    parser = argparse.ArgumentParser()
    parser.add_argument('--cwd', required=True)
    parser.add_argument('--log', required=True)
    args = parser.parse_args(argv[:split])
    command = argv[split + 1:]
    if os.path.exists(args.log) and os.path.getsize(args.log) > MAX_LOG_BYTES:
        os.replace(args.log, args.log + '.1')
    log = open(args.log, 'ab')
    lift_inherited_limits()
    process = subprocess.Popen(command, cwd=args.cwd, stdin=subprocess.DEVNULL, stdout=log,
                               stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
    print(process.pid)
    return 0


if __name__ == '__main__':
    sys.exit(main())
