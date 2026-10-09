#!/usr/bin/env python3
"""Prepare the LinkedIn engine for Odoo ("Prepare engine" in Settings).

Started by Odoo as a detached process; standard library only. Installs, inside
<engine root> (a folder of Odoo's data dir), without root rights:

* uv (a single binary) into <root>/bin,
* a Python >= 3.12.4: Odoo's own Python when it is new enough, otherwise a
  private one downloaded by uv into <root>/python,
* a private environment <root>/env with mcp-server-linkedin (pinned version),
* the Chromium build the engine uses, shared by every account, in <root>/browsers.

Progress is written to <root>/prepare.json (read by Odoo) and the full output to
<root>/prepare.log. Safe to run again: finished steps are skipped.

    python3 installer.py <root> --odoo-python /path/to/odoo/python [--simulate]
"""
import argparse
import glob
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request

ENGINE_PACKAGE = 'mcp-server-linkedin'
ENGINE_VERSION = '4.26.2'
MIN_PYTHON = (3, 12, 4)
MAX_PYTHON = (3, 15, 0)          # exclusive
PRIVATE_PYTHON = '3.12'
UV_URL = 'https://github.com/astral-sh/uv/releases/latest/download/uv-{arch}-unknown-linux-gnu.tar.gz'
STEPS = [
    ('uv', 'Download the installer (uv)'),
    ('python', 'Python for the engine'),
    ('environment', 'Private environment'),
    ('engine', 'LinkedIn engine %s %s' % (ENGINE_PACKAGE, ENGINE_VERSION)),
    ('browser', 'Chromium browser'),
    ('check', 'Health check'),
]


class Installer:
    def __init__(self, root, odoo_python, simulate=False):
        self.root = os.path.abspath(root)
        self.odoo_python = odoo_python
        self.simulate = simulate
        self.status_path = os.path.join(self.root, 'prepare.json')
        self.log_path = os.path.join(self.root, 'prepare.log')
        self.status = {
            'state': 'running', 'pid': os.getpid(), 'step': None, 'steps': [s for s, _l in STEPS],
            'done_steps': [], 'message': 'Starting', 'started': time.time(), 'finished': None,
            'engine_version': None, 'python': None, 'error': None, 'simulated': simulate,
        }
        os.makedirs(self.root, exist_ok=True)
        self.log = open(self.log_path, 'a', buffering=1)

    # -- helpers -------------------------------------------------------------
    def save(self, **values):
        self.status.update(values)
        tmp = self.status_path + '.tmp'
        with open(tmp, 'w') as handle:
            json.dump(self.status, handle)
        os.replace(tmp, self.status_path)

    def say(self, text):
        self.log.write('[%s] %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), text))

    def run(self, cmd, env=None, timeout=1800):
        self.say('$ ' + ' '.join(cmd))
        full_env = dict(os.environ, **(env or {}))
        subprocess.run(cmd, stdout=self.log, stderr=subprocess.STDOUT, check=True, env=full_env,
                       timeout=timeout, cwd=self.root)

    def output(self, cmd, env=None):
        full_env = dict(os.environ, **(env or {}))
        return subprocess.run(cmd, capture_output=True, text=True, check=True, env=full_env,
                              cwd=self.root, timeout=120).stdout.strip()

    @property
    def uv(self):
        return os.path.join(self.root, 'bin', 'uv')

    @property
    def env_python(self):
        return os.path.join(self.root, 'env', 'bin', 'python')

    def uv_env(self):
        return {
            'UV_PYTHON_INSTALL_DIR': os.path.join(self.root, 'python'),
            'UV_CACHE_DIR': os.path.join(self.root, 'cache'),
            'UV_NO_CONFIG': '1',
        }

    def python_version(self, python):
        try:
            text = self.output([python, '-c', 'import sys; print("%d.%d.%d" % sys.version_info[:3])'])
            return tuple(int(x) for x in text.split('.'))
        except (OSError, subprocess.SubprocessError, ValueError):
            return None

    # -- steps -----------------------------------------------------------------
    def step_uv(self):
        if os.path.exists(self.uv):
            return 'already present'
        arch = {'x86_64': 'x86_64', 'amd64': 'x86_64', 'aarch64': 'aarch64', 'arm64': 'aarch64'}.get(
            platform.machine().lower())
        if not arch or not sys.platform.startswith('linux'):
            raise RuntimeError('Unsupported platform %s %s: the engine needs Linux on x86_64 or aarch64'
                               % (sys.platform, platform.machine()))
        url = UV_URL.format(arch=arch)
        self.say('download ' + url)
        with urllib.request.urlopen(url, timeout=120) as response:
            data = response.read()
        os.makedirs(os.path.dirname(self.uv), exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
            member = next(m for m in archive.getmembers() if m.isfile() and os.path.basename(m.name) == 'uv')
            with archive.extractfile(member) as source, open(self.uv + '.tmp', 'wb') as target:
                shutil.copyfileobj(source, target)
        os.chmod(self.uv + '.tmp', 0o755)
        os.replace(self.uv + '.tmp', self.uv)
        return self.output([self.uv, '--version'])

    def step_python(self):
        version = self.python_version(self.odoo_python) if self.odoo_python else None
        if version and MIN_PYTHON <= version < MAX_PYTHON:
            self.chosen_python = self.odoo_python
            label = "Odoo's Python %s" % '.'.join(map(str, version))
        else:
            self.run([self.uv, 'python', 'install', PRIVATE_PYTHON], env=self.uv_env())
            self.chosen_python = PRIVATE_PYTHON
            label = 'private Python %s (Odoo has %s)' % (
                PRIVATE_PYTHON, '.'.join(map(str, version)) if version else 'none usable')
        self.save(python=label)
        return label

    def step_environment(self):
        if os.path.exists(self.env_python):
            version = self.python_version(self.env_python)
            if version and MIN_PYTHON <= version < MAX_PYTHON:
                return 'already present (Python %s)' % '.'.join(map(str, version))
            shutil.rmtree(os.path.join(self.root, 'env'))
        args = [self.uv, 'venv', os.path.join(self.root, 'env'), '--python', self.chosen_python]
        if self.chosen_python == PRIVATE_PYTHON:
            args += ['--python-preference', 'only-managed']
        self.run(args, env=self.uv_env())
        return 'created'

    def step_engine(self):
        self.run([self.uv, 'pip', 'install', '--python', self.env_python,
                  '%s==%s' % (ENGINE_PACKAGE, ENGINE_VERSION)], env=self.uv_env())
        version = self.output([self.env_python, '-c',
                               'import importlib.metadata as m; print(m.version("%s"))' % ENGINE_PACKAGE])
        self.copy_licenses()
        self.save(engine_version=version)
        return version

    def copy_licenses(self):
        """Keep the engine's LICENSE and NOTICE (Apache-2.0) next to the install."""
        target = os.path.join(self.root, 'licenses', ENGINE_PACKAGE)
        os.makedirs(target, exist_ok=True)
        pattern = os.path.join(self.root, 'env', 'lib', 'python3*', 'site-packages',
                               'mcp_server_linkedin-*.dist-info', '**')
        for path in glob.glob(pattern, recursive=True):
            if os.path.isfile(path) and os.path.basename(path) in ('LICENSE', 'NOTICE'):
                shutil.copy(path, target)

    def step_browser(self):
        env = {'PLAYWRIGHT_BROWSERS_PATH': os.path.join(self.root, 'browsers')}
        self.run([self.env_python, '-m', 'patchright', 'install', 'chromium'], env=env)
        return 'installed'

    def step_check(self):
        chrome = sorted(glob.glob(os.path.join(self.root, 'browsers', 'chromium-*', 'chrome-linux*', 'chrome')))
        if not chrome:
            return 'browser binary not found'
        try:
            ldd = subprocess.run(['ldd', chrome[-1]], capture_output=True, text=True, timeout=60).stdout
        except (OSError, subprocess.SubprocessError):
            return 'ldd not available'
        missing = sorted({line.split()[0] for line in ldd.splitlines() if 'not found' in line})
        return 'missing system libraries: %s' % ', '.join(missing) if missing else 'system libraries ok'

    # -- main ----------------------------------------------------------------
    def simulate_step(self, key):
        time.sleep(0.05)
        if key == 'engine':
            os.makedirs(os.path.join(self.root, 'env', 'bin'), exist_ok=True)
            self.save(engine_version=ENGINE_VERSION + '-simulated')
        if key == 'python':
            self.save(python='simulated')
        return 'simulated'

    def main(self):
        self.save()
        self.say('prepare engine: root=%s simulate=%s' % (self.root, self.simulate))
        try:
            for key, label in STEPS:
                self.save(step=key, message=label + '…')
                self.say('== ' + label)
                result = self.simulate_step(key) if self.simulate else getattr(self, 'step_' + key)()
                self.say('-> %s' % result)
                self.status['done_steps'].append(key)
                self.save(message='%s: %s' % (label, result))
        except Exception as exc:          # report any failure to Odoo, then exit non-zero
            self.say('FAILED: %r' % exc)
            self.save(state='failed', error='%s: %s' % (exc.__class__.__name__, exc), finished=time.time(),
                      message='Failed during "%s"' % dict(STEPS).get(self.status['step'], self.status['step']))
            return 1
        self.save(state='done', step=None, finished=time.time(), message='Engine ready')
        self.say('done')
        return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('root')
    parser.add_argument('--odoo-python', default='')
    parser.add_argument('--simulate', action='store_true', help='no download, for tests')
    args = parser.parse_args(argv)
    return Installer(args.root, args.odoo_python, args.simulate).main()


if __name__ == '__main__':
    sys.exit(main())
