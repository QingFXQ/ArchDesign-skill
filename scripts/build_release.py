"""Build the public release tree from the development checkout.

The public repository is a whitelist snapshot: private project evidence, the
migration reports and anything machine-specific never enter it. The builder
copies the allowed files, writes a manifest with per-file hashes and refuses to
finish when a private path or a credential is still present.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = 'skills/architecture-design-workflow'
MANIFEST = 'RELEASE-MANIFEST.json'
MAX_FILE_BYTES = 50 * 1024 * 1024
SKIP_PARTS = {'__pycache__', '.pytest_cache', '.venv', '.mypy_cache'}
# Copy these paths as-is (minus the exclusions below).
INCLUDE_DIRS = ('.github', 'docs', 'scripts', 'tests', SKILL)
INCLUDE_FILES = ('README.md', 'CONTRIBUTING.md', 'CODE_OF_CONDUCT.md', 'SECURITY.md',
                 'SUPPORT.md', 'LICENSE', 'requirements-dev.txt', '.gitignore')
# Paths that only make sense in the private development checkout.
EXCLUDE_FILES = {
    'docs/open-source-audit.md',          # private repository audit
    'scripts/check_external_links.py',    # reads audit/repository-check.json
}
EXCLUDE_PREFIXES = (
    f'{SKILL}/assets/history/',           # real course projects and models
)
# A release must not contain these strings; they identify a private checkout.
PRIVATE_MARKERS = ('01_文档资料', 'wuchang-library', '武昌图书馆', 'CAAAAAD')
SECRETS = (
    ('github token', re.compile(r'\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}')),
    ('github pat', re.compile(r'\bgithub_pat_[A-Za-z0-9_]{20,}')),
    ('api key', re.compile(r'\b(?:sk|rk)-[A-Za-z0-9]{20,}')),
    ('aws key', re.compile(r'\bAKIA[0-9A-Z]{16}\b')),
    ('private key', re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')),
)
TEXT_SUFFIXES = {'.md', '.py', '.js', '.mjs', '.json', '.yml', '.yaml', '.toml', '.txt',
                 '.gitignore'}
FAKE = 'fakecredential'


def included(relative):
    if relative in EXCLUDE_FILES:
        return False
    return not any(relative.startswith(prefix) for prefix in EXCLUDE_PREFIXES)


def files():
    rows = []
    for name in INCLUDE_FILES:
        path = ROOT / name
        if path.is_file():
            rows.append(path)
    for directory in INCLUDE_DIRS:
        for path in (ROOT / directory).rglob('*'):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT).as_posix()
            if any(part in SKIP_PARTS for part in Path(relative).parts):
                continue
            if path.suffix in ('.pyc', '.pyo'):
                continue
            if not included(relative):
                continue
            rows.append(path)
    return sorted(set(rows))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def head():
    try:
        return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True,
                              text=True, encoding='utf-8', timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ''


def inspect(path, relative):
    """Problems that must block a release: credentials, private markers, size."""
    problems = []
    if relative == 'scripts/build_release.py':
        return problems  # it names the markers it looks for
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        problems.append(f'oversized ({size} bytes): {relative}')
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name != '.gitignore':
        return problems
    try:
        text = path.read_text(encoding='utf-8-sig')
    except (UnicodeError, OSError):
        return problems
    for marker in PRIVATE_MARKERS:
        if marker in text:
            problems.append(f'private marker {marker!r}: {relative}')
    for number, line in enumerate(text.splitlines(), 1):
        if FAKE in line.lower():
            continue
        for label, pattern in SECRETS:
            if pattern.search(line):
                problems.append(f'possible {label}: {relative}:{number}')
    return problems


def build(out, check_only=False, force=False):
    out = Path(out).expanduser().resolve()
    if out == ROOT or ROOT in out.parents:
        raise SystemExit('the release directory must be outside the development checkout')
    rows = files()
    problems = []
    for path in rows:
        problems.extend(inspect(path, path.relative_to(ROOT).as_posix()))
    if problems:
        return {'written': 0, 'problems': problems, 'out': str(out)}
    # Check-only must not touch the target: an existing release stays byte-identical
    # even when --force is passed, because --force only governs writing.
    if check_only:
        return {'written': 0, 'problems': [], 'files': len(rows), 'out': str(out)}
    if out.exists() and any(out.iterdir()):
        if not force:
            raise SystemExit(f'{out} is not empty; pass --force to replace it')
        shutil.rmtree(out)
    for path in rows:
        relative = path.relative_to(ROOT)
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    manifest = {
        'schema_version': 1,
        'built_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'source_head': head(),
        'files': [{'path': path.relative_to(ROOT).as_posix(),
                   'bytes': path.stat().st_size,
                   'sha256': digest(path)} for path in rows],
        'excluded': sorted(EXCLUDE_FILES) + list(EXCLUDE_PREFIXES),
        'total_bytes': sum(path.stat().st_size for path in rows),
    }
    (out / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n',
                                encoding='utf-8')
    return {'written': len(rows), 'problems': [], 'out': str(out),
            'total_bytes': manifest['total_bytes']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, help='target directory, outside the checkout')
    parser.add_argument('--check', action='store_true', help='scan only, copy nothing')
    parser.add_argument('--force', action='store_true', help='replace a non-empty target')
    args = parser.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    result = build(args.out, check_only=args.check, force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result['problems'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
