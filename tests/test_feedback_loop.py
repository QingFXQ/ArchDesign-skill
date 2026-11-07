"""Feedback lifecycle, similar-issue retrieval and reviewed lesson write-back."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/architecture-design-workflow/scripts'
FEEDBACK = SCRIPTS / 'feedback.py'
SKILL = ROOT / 'skills/architecture-design-workflow'
ENV = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')


def cli(*args, cwd=None):
    return subprocess.run([sys.executable, '-X', 'utf8', str(args[0]), *map(str, args[1:])],
                          cwd=cwd, env=ENV, capture_output=True, text=True,
                          encoding='utf-8', timeout=120)


class FeedbackCase(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory(prefix='建筑 反馈 loop ')
        self.base = Path(self._temporary.name)
        (self.base / 'project.json').write_text(
            json.dumps({'schema_version': 2, 'revision': 'R2', 'stage': 'presentation',
                        'brief': 'fixture', 'artifacts': [], 'decisions': [],
                        'validations': [], 'requirements': [], 'history': []}), encoding='utf-8')
        (self.base / 'boards.pdf').write_text('board bytes', encoding='utf-8')
        (self.base / 'screenshot.png').write_text('png bytes', encoding='utf-8')

    def tearDown(self):
        self._temporary.cleanup()

    def run_cli(self, *args, ok=True):
        result = cli(FEEDBACK, '--root', self.base, *args, cwd=self.base)
        try:
            payload = json.loads(result.stdout or result.stderr)
        except json.JSONDecodeError:
            self.fail('non-JSON command output: ' + result.stdout + result.stderr)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return payload

    def report(self, text='图名双横线压住字了', tag='双横线'):
        return self.run_cli('report', '--user-text', text, '--expected', '双横线不压图名',
                            '--actual', '双横线压图名 5mm', '--category', 'layout',
                            '--tag', tag, '--artifact', 'boards.pdf',
                            '--evidence', 'screenshot.png',
                            '--step', 'open page 1 of boards.pdf')['feedback']

    def verified(self, text='图名双横线压住字了'):
        record = self.report(text)
        key = record['id']
        self.run_cli('reproduce', '--id', key, '--note', 'reproduced on page 1')
        self.run_cli('diagnose', '--id', key, '--root-cause-status', 'confirmed',
                     '--root-cause', 'title band reserves less height than the glyph box',
                     '--evidence', 'screenshot.png')
        self.run_cli('fix', '--id', key, '--summary', 'reserve 2 mm more for the title band',
                     '--commit', '3f2a91c',
                     '--regression-test', 'tests/test_delivery_gates.py::LayoutTitleBand')
        self.run_cli('verify', '--id', key, '--result', 'passed', '--note', 'regression passed')
        return key

    def feedback(self, key):
        return self.run_cli('show', '--id', key)['feedback']


class FeedbackRecordTests(FeedbackCase):
    def test_record_keeps_every_required_field_and_its_history(self):
        record = self.report()
        self.assertEqual(record['status'], 'reported')
        self.assertEqual(record['revision'], 'R2')
        self.assertEqual(record['project'], self.base.name)
        self.assertEqual(record['artifacts'][0]['path'], 'boards.pdf')
        self.assertEqual(len(record['artifacts'][0]['sha256']), 64)
        self.assertEqual(record['evidence'][0]['path'], 'screenshot.png')
        self.assertEqual(record['steps'], ['open page 1 of boards.pdf'])
        self.assertEqual(record['root_cause']['status'], 'unknown')
        for key in ('user_text', 'expected', 'actual', 'category', 'tags'):
            self.assertTrue(record[key], key)
        self.assertIsNone(record['duplicate_of'])
        self.assertEqual([row['to'] for row in record['history']], ['reported'])

    def test_full_lifecycle_is_ordered_and_readable(self):
        key = self.verified()
        record = self.feedback(key)
        self.assertEqual(record['status'], 'regression_verified')
        self.assertEqual([row['to'] for row in record['history']],
                         ['reported', 'reproduced', 'diagnosed', 'fixed', 'regression_verified'])
        self.assertEqual(record['root_cause']['status'], 'confirmed')
        self.assertTrue(record['root_cause']['evidence'])
        self.assertEqual(record['fix']['commit'], '3f2a91c')
        self.assertEqual(record['verification']['result'], 'passed')

    def test_artifact_hash_records_the_state_at_report_time(self):
        record = self.report()
        recorded = record['artifacts'][0]['sha256']
        (self.base / 'boards.pdf').write_text('board bytes, revised later', encoding='utf-8')
        self.assertEqual(self.feedback(record['id'])['artifacts'][0]['sha256'], recorded)
        self.assertNotEqual(hashlib.sha256((self.base / 'boards.pdf').read_bytes()).hexdigest(),
                            recorded)

    def test_evidence_outside_the_project_is_refused(self):
        outside = self.base.parent / 'outside-evidence.png'
        outside.write_text('outside', encoding='utf-8')
        try:
            self.run_cli('report', '--user-text', 'x', '--expected', 'y', '--actual', 'z',
                         '--evidence', str(outside), ok=False)
        finally:
            outside.unlink()
        self.assertFalse((self.base / 'feedback.json').exists())


class RootCauseHonestyTests(FeedbackCase):
    def test_confirmed_root_cause_cannot_skip_reproduction(self):
        record = self.report()
        self.run_cli('diagnose', '--id', record['id'], '--root-cause-status', 'confirmed',
                     '--root-cause', 'guess', '--evidence', 'screenshot.png', ok=False)
        self.assertEqual(self.feedback(record['id'])['root_cause']['status'], 'unknown')

    def test_confirmed_root_cause_needs_evidence(self):
        record = self.report()
        self.run_cli('reproduce', '--id', record['id'])
        self.run_cli('diagnose', '--id', record['id'], '--root-cause-status', 'confirmed',
                     '--root-cause', 'very likely the title band', ok=False)
        self.assertEqual(self.feedback(record['id'])['root_cause']['status'], 'unknown')

    def test_suspected_root_cause_stays_labelled_as_suspected(self):
        record = self.report()
        self.run_cli('reproduce', '--id', record['id'])
        self.run_cli('diagnose', '--id', record['id'], '--root-cause-status', 'suspected',
                     '--root-cause', 'probably the title band height')
        stored = self.feedback(record['id'])
        self.assertEqual(stored['root_cause']['status'], 'suspected')
        self.assertEqual(stored['history'][-1]['to'], 'diagnosed')

    def test_report_keeps_a_supplied_suspected_root_cause(self):
        record = self.run_cli('report', '--user-text', '图名压线', '--expected', '不压',
                              '--actual', '压住了', '--root-cause-status', 'suspected',
                              '--root-cause', '标题带预留高度不足')['feedback']
        self.assertEqual(record['root_cause'], {'status': 'suspected',
                                                'text': '标题带预留高度不足',
                                                'evidence': []})
        self.assertEqual(self.feedback(record['id'])['root_cause']['status'], 'suspected')

    def test_report_without_a_root_cause_stays_unknown(self):
        record = self.report()
        self.assertEqual(record['root_cause'], {'status': 'unknown', 'text': '', 'evidence': []})

    def test_a_reported_suspicion_can_still_be_confirmed_through_diagnose(self):
        record = self.run_cli('report', '--user-text', '图名压线', '--expected', '不压',
                              '--actual', '压住了', '--root-cause-status', 'suspected',
                              '--root-cause', '怀疑标题带')['feedback']
        key = record['id']
        self.run_cli('reproduce', '--id', key, '--note', 'reproduced')
        confirmed = self.run_cli('diagnose', '--id', key, '--root-cause-status', 'confirmed',
                                 '--root-cause', '标题带高度小于字形', '--evidence', 'screenshot.png')
        self.assertEqual(confirmed['root_cause']['status'], 'confirmed')
        self.assertTrue(confirmed['root_cause']['evidence'])
        self.assertEqual(confirmed['status'], 'diagnosed')

    def test_report_time_cannot_claim_a_confirmed_root_cause(self):
        self.run_cli('report', '--user-text', 'x', '--expected', 'y', '--actual', 'z',
                     '--root-cause-status', 'confirmed', '--root-cause', 'certain', ok=False)

    def test_lifecycle_cannot_skip_from_reported_to_fixed(self):
        record = self.report()
        self.run_cli('fix', '--id', record['id'], '--summary', 'quick patch', ok=False)
        self.assertEqual(self.feedback(record['id'])['status'], 'reported')


class SimilarIssueTests(FeedbackCase):
    def test_search_finds_the_earlier_issue_by_keywords_and_tags(self):
        first = self.report('图名双横线压住字了', '双横线')
        second = self.report('另一张板子的双横线也压字', '双横线')
        found = self.run_cli('search', '--query', '双横线 压 图名')
        ids = [row['id'] for row in found['results']]
        self.assertEqual(ids[0], first['id'])
        self.assertIn(second['id'], ids)
        self.assertTrue(found['results'][0]['matched'])
        tagged = self.run_cli('search', '--query', '双横线', '--tag', '双横线')
        self.assertEqual(len(tagged['results']), 2)
        by_category = self.run_cli('search', '--query', '双横线', '--category', 'presentation')
        self.assertEqual(by_category['results'], [])

    def test_new_report_surfaces_similar_history_before_analysis_starts(self):
        first = self.report('图名双横线压住字了', '双横线')
        again = self.run_cli('report', '--user-text', '双横线又压字了', '--expected', '不压图名',
                             '--actual', '压住了', '--category', 'layout', '--tag', '双横线')
        self.assertEqual([row['id'] for row in again['similar']], [first['id']])
        shown = self.run_cli('show', '--id', first['id'])
        self.assertEqual([row['id'] for row in shown['similar']], [again['feedback']['id']],
                         'a record never lists itself as its own neighbour')

    def test_search_returns_the_previous_fix_instead_of_only_the_complaint(self):
        key = self.verified()
        row = self.run_cli('search', '--query', '双横线 压 图名')['results'][0]
        self.assertEqual(row['id'], key)
        self.assertEqual(row['status'], 'regression_verified')
        self.assertEqual(row['root_cause'], 'confirmed')
        self.assertIn('title band', row['fix'])
        self.assertEqual(row['regression_tests'],
                         ['tests/test_delivery_gates.py::LayoutTitleBand'])

    def test_duplicate_link_is_recorded_once_and_traceable(self):
        first = self.report()
        second = self.report('重复的问题')
        linked = self.run_cli('link', '--id', second['id'], '--duplicate-of', first['id'])['feedback']
        self.assertEqual(linked['duplicate_of'], first['id'])
        self.assertIn('linked to ' + first['id'], [row['note'] for row in linked['history']])
        self.run_cli('link', '--id', first['id'], '--duplicate-of', first['id'], ok=False)


class RegressionLinkTests(FeedbackCase):
    def test_verified_fix_records_the_regression_test(self):
        key = self.verified()
        record = self.feedback(key)
        self.assertEqual(record['regression']['tests'],
                         ['tests/test_delivery_gates.py::LayoutTitleBand'])
        self.assertEqual(record['regression']['result'], 'passed')

    def test_verification_without_a_regression_test_is_refused(self):
        record = self.report()
        key = record['id']
        self.run_cli('reproduce', '--id', key)
        self.run_cli('diagnose', '--id', key, '--root-cause-status', 'suspected',
                     '--root-cause', 'title band')
        self.run_cli('fix', '--id', key, '--summary', 'widened the band')
        self.run_cli('verify', '--id', key, '--result', 'passed', ok=False)
        self.assertEqual(self.feedback(key)['status'], 'fixed')

    def test_failed_regression_keeps_the_issue_open(self):
        record = self.report()
        key = record['id']
        self.run_cli('reproduce', '--id', key)
        self.run_cli('diagnose', '--id', key, '--root-cause-status', 'suspected',
                     '--root-cause', 'title band')
        self.run_cli('fix', '--id', key, '--summary', 'widened the band',
                     '--regression-test', 'tests/x.py::y')
        failed = self.run_cli('verify', '--id', key, '--result', 'failed')
        self.assertEqual(failed['status'], 'fixed')
        self.assertEqual(failed['regression']['result'], 'failed')

    def test_pending_and_project_specific_keep_a_reason(self):
        key = self.report()['id']
        self.run_cli('mark', '--id', key, '--status', 'pending', '--reason', 'awaiting the next review')
        self.assertEqual(self.feedback(key)['status'], 'pending')
        self.assertEqual(self.feedback(key)['reason'], 'awaiting the next review')
        self.run_cli('mark', '--id', key, '--status', 'project_specific', ok=False)
        self.run_cli('mark', '--id', key, '--status', 'project_specific',
                     '--reason', 'course-specific paper size', ok=True)
        self.assertEqual(self.feedback(key)['status'], 'project_specific')


class LessonWriteBackTests(FeedbackCase):
    def test_unverified_feedback_cannot_become_a_lesson(self):
        record = self.report()
        self.run_cli('lesson', 'candidate', '--source', record['id'], '--target', 'process',
                     '--text', 'a rule from a single complaint', ok=False)
        stored = json.loads((self.base / 'feedback.json').read_text(encoding='utf-8'))
        self.assertEqual(stored['lessons'], [])

    def test_candidate_stays_pending_until_a_named_human_review(self):
        key = self.verified()
        lesson = self.run_cli('lesson', 'candidate', '--source', key, '--target', 'process',
                              '--text', 'reserve the title band from the real glyph box',
                              '--document', 'references/verification.md',
                              '--evidence', 'screenshot.png')['lesson']
        self.assertEqual(lesson['status'], 'pending_validation')
        self.assertEqual(lesson['source_feedback'], [key])
        self.run_cli('lesson', 'apply', '--id', lesson['id'],
                     '--document', 'references/verification.md', '--commit', '3f2a91c', ok=False)
        self.run_cli('lesson', 'validate', '--id', lesson['id'], '--reviewed-by', '   ', ok=False)
        still = self.run_cli('lesson', 'show', '--id', lesson['id'])
        self.assertEqual(still['status'], 'pending_validation')

    def test_applied_lesson_records_source_evidence_and_commit_without_editing_the_document(self):
        key = self.verified()
        lesson = self.run_cli('lesson', 'candidate', '--source', key, '--target', 'process',
                              '--text', 'reserve the title band from the real glyph box',
                              '--document', 'references/verification.md')['lesson']
        self.run_cli('lesson', 'validate', '--id', lesson['id'], '--reviewed-by', '课程指导教师',
                     '--evidence', 'screenshot.png')
        target = SKILL / 'references/verification.md'
        before = hashlib.sha256(target.read_bytes()).hexdigest()
        applied = self.run_cli('lesson', 'apply', '--id', lesson['id'],
                               '--document', 'references/verification.md',
                               '--commit', 'ab12cd9')['lesson']
        self.assertEqual(applied['status'], 'applied')
        self.assertEqual(applied['document'], 'references/verification.md')
        self.assertEqual(applied['commit'], 'ab12cd9')
        self.assertEqual(applied['reviewed_by'], '课程指导教师')
        self.assertEqual(applied['source_feedback'], [key])
        self.assertTrue(applied['evidence'])
        self.assertEqual(before, hashlib.sha256(target.read_bytes()).hexdigest(),
                         'the tool records the change; it does not rewrite skill documents')

    def test_lesson_cannot_be_applied_outside_the_skill(self):
        key = self.verified()
        lesson = self.run_cli('lesson', 'candidate', '--source', key, '--target', 'skill_section',
                              '--text', 'a claim')['lesson']
        self.run_cli('lesson', 'validate', '--id', lesson['id'], '--reviewed-by', 'reviewer',
                     '--evidence', 'screenshot.png')
        self.run_cli('lesson', 'apply', '--id', lesson['id'],
                     '--document', str(self.base / 'boards.pdf'), '--commit', 'ab12cd9', ok=False)
        self.run_cli('lesson', 'apply', '--id', lesson['id'],
                     '--document', 'references/verification.md', '--commit', 'zzz', ok=False)
        self.assertEqual(self.run_cli('lesson', 'show', '--id', lesson['id'])['status'], 'validated')

    def test_rejected_lesson_keeps_its_reason(self):
        key = self.verified()
        lesson = self.run_cli('lesson', 'candidate', '--source', key, '--target', 'tool',
                              '--text', 'tool change')['lesson']
        rejected = self.run_cli('lesson', 'reject', '--id', lesson['id'],
                                '--note', 'single project preference, not a general rule')['lesson']
        self.assertEqual(rejected['status'], 'rejected')
        self.assertEqual(rejected['reason'], 'single project preference, not a general rule')

    def test_status_summarises_open_feedback_and_lessons(self):
        key = self.verified()
        self.run_cli('lesson', 'candidate', '--source', key, '--target', 'process', '--text', 'x')
        self.report('still open')
        counts = self.run_cli('status')
        self.assertEqual(counts['feedback'], 2)
        self.assertEqual(counts['open'], 1)
        self.assertEqual(counts['lessons'], 1)
        self.assertEqual(counts['lessons_by_status']['pending_validation'], 1)


if __name__ == '__main__':
    unittest.main()
