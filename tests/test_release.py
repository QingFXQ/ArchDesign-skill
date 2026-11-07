"""The public release must be self-contained, private-free and runnable on its own."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / 'scripts/build_release.py'
SKILL = 'skills/architecture-design-workflow'


class ReleaseSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._temporary = tempfile.TemporaryDirectory(prefix='archdesigh release ')
        cls.out = Path(cls._temporary.name) / 'public'
        result = subprocess.run([sys.executable, '-X', 'utf8', str(BUILDER), '--out', str(cls.out)],
                                capture_output=True, text=True, encoding='utf-8', timeout=300,
                                cwd=ROOT)
        if result.returncode != 0:
            raise AssertionError(result.stdout[-3000:] + result.stderr[-2000:])
        cls.report = json.loads(result.stdout)
        cls.manifest = json.loads((cls.out / 'RELEASE-MANIFEST.json').read_text(encoding='utf-8'))

    @classmethod
    def tearDownClass(cls):
        cls._temporary.cleanup()

    def test_private_assets_and_reports_are_absent(self):
        for relative in ('audit', f'{SKILL}/assets/history', 'docs/open-source-audit.md',
                         'web'):
            self.assertFalse((self.out / relative).exists(), relative)
        names = {row['path'] for row in self.manifest['files']}
        self.assertFalse([name for name in names if name.startswith('audit/')])
        self.assertFalse([name for name in names if '/assets/history/' in name])

    def test_skill_entry_and_tools_survive(self):
        for relative in (f'{SKILL}/SKILL.md', f'{SKILL}/scripts/project.py',
                         f'{SKILL}/scripts/feedback.py', f'{SKILL}/scripts/check_layout.py',
                         f'{SKILL}/references/knowledge/README.md',
                         f'{SKILL}/references/knowledge/design-knowledge.md',
                         f'{SKILL}/assets/knowledge/'
                         'architecture-case-rag/index/cases.json',
                         'tests/test_delivery_gates.py', 'LICENSE', 'docs/licensing.md'):
            self.assertTrue((self.out / relative).is_file(), relative)

    def test_manifest_matches_the_copied_bytes(self):
        self.assertEqual(len(self.manifest['files']), self.report['written'])
        for row in self.manifest['files']:
            path = self.out / row['path']
            self.assertEqual(path.stat().st_size, row['bytes'], row['path'])
        self.assertEqual(self.manifest['total_bytes'],
                         sum(row['bytes'] for row in self.manifest['files']))

    def test_mit_licence_ships_with_the_release(self):
        text = (self.out / 'LICENSE').read_text(encoding='utf-8')
        self.assertTrue(text.startswith('MIT License'))
        self.assertIn('Copyright (c) 2026 QingFXQ', text)
        self.assertFalse((self.out / 'docs/license-drafts').exists(),
                         'superseded licence drafts must not ship')

    def test_release_passes_its_own_repository_audit(self):
        result = subprocess.run([sys.executable, '-X', 'utf8',
                                 str(self.out / 'scripts/audit_repository.py'), '--check'],
                                capture_output=True, text=True, encoding='utf-8', timeout=300,
                                cwd=self.out)
        self.assertEqual(result.returncode, 0, result.stdout[-3000:])
        self.assertIn('"errors": []', result.stdout)

    def test_release_can_initialize_and_record_an_issue(self):
        work = Path(self._temporary.name) / 'project'
        work.mkdir()
        scripts = self.out / SKILL / 'scripts'
        init = subprocess.run([sys.executable, '-X', 'utf8', str(scripts / 'project.py'),
                               '--root', str(work), 'init', '--brief', 'release smoke'],
                              capture_output=True, text=True, encoding='utf-8', timeout=120)
        self.assertEqual(init.returncode, 0, init.stderr[-1500:])
        record = subprocess.run(
            [sys.executable, '-X', 'utf8', str(scripts / 'feedback.py'), '--root', str(work),
             'report', '--user-text', '快照自检', '--expected', '正常', '--actual', '异常'],
            capture_output=True, text=True, encoding='utf-8', timeout=120)
        self.assertEqual(record.returncode, 0, record.stderr[-1500:])
        self.assertEqual(json.loads(record.stdout)['feedback']['status'], 'reported')


class CheckModeSafetyTests(unittest.TestCase):
    """--check promises a read-only scan; it must never erase an existing release."""

    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory(prefix='archdesigh release check ')
        self.out = Path(self._temporary.name) / 'existing-release'
        self.out.mkdir()
        self.sentinel = self.out / 'SENTINEL.txt'
        self.sentinel.write_text('do not touch\n', encoding='utf-8')
        self.extra = self.out / 'previous-release.md'
        self.extra.write_text('previous release content\n', encoding='utf-8')

    def tearDown(self):
        self._temporary.cleanup()

    def run_builder(self, *args):
        return subprocess.run([sys.executable, '-X', 'utf8', str(BUILDER),
                               '--out', str(self.out), *args],
                              capture_output=True, text=True, encoding='utf-8',
                              timeout=300, cwd=ROOT)

    def snapshot(self):
        return sorted((path.relative_to(self.out).as_posix(), path.read_bytes())
                      for path in self.out.rglob('*') if path.is_file())

    def assert_untouched(self, before):
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.sentinel.read_text(encoding='utf-8'), 'do not touch\n')
        self.assertEqual(self.extra.read_text(encoding='utf-8'),
                         'previous release content\n')

    def test_check_with_force_does_not_delete_or_modify_the_release(self):
        before = self.snapshot()
        result = self.run_builder('--check', '--force')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['written'], 0)
        self.assert_untouched(before)
        self.assertFalse((self.out / 'RELEASE-MANIFEST.json').exists())

    def test_check_without_force_scans_an_existing_directory(self):
        before = self.snapshot()
        result = self.run_builder('--check')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertGreater(json.loads(result.stdout)['files'], 0)
        self.assert_untouched(before)
        self.assertFalse((self.out / 'RELEASE-MANIFEST.json').exists())

    def test_writing_without_force_refuses_and_preserves_the_release(self):
        before = self.snapshot()
        result = self.run_builder()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not empty', result.stderr)
        self.assert_untouched(before)

    def test_force_still_replaces_the_directory_when_writing(self):
        result = self.run_builder('--force')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.sentinel.exists(), '--force must replace the old release')
        self.assertTrue((self.out / 'RELEASE-MANIFEST.json').is_file())
        self.assertTrue((self.out / SKILL / 'SKILL.md').is_file())


if __name__ == '__main__':
    unittest.main()
