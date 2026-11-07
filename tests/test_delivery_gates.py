"""Artifact lifecycle, delivery requirements and review binding on real CLI paths."""
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
PROJECT = SCRIPTS / 'project.py'
ENV = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
LAYOUT = {'paper_mm': [594, 841],
          'pages': [{'items': [{'id': 'plan', 'rect_mm': [10, 10, 200, 200]}]}]}


def cli(script, *args, cwd=None):
    return subprocess.run([sys.executable, '-X', 'utf8', str(script), *map(str, args)],
                          cwd=cwd, env=ENV, capture_output=True, text=True,
                          encoding='utf-8', timeout=120)


class GateCase(unittest.TestCase):
    """Each case owns a project directory whose name contains spaces and Chinese."""

    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory(prefix='设计 project gate ')
        self.base = Path(self._temporary.name)

    def tearDown(self):
        self._temporary.cleanup()

    def run_cli(self, *args, ok=True):
        result = cli(PROJECT, '--root', self.base, *args, cwd=self.base)
        payload = json.loads(result.stdout or result.stderr)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return payload

    def write(self, name, text):
        path = self.base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def board(self, name, text):
        import pymupdf as fitz
        document = fitz.open()
        page = document.new_page(width=594 * 72 / 25.4, height=841 * 72 / 25.4)
        page.insert_text((40, 60), text)
        document.save(self.base / name)
        document.close()

    def state(self):
        return json.loads((self.base / 'project.json').read_text(encoding='utf-8'))

    def artifact(self, name):
        return next(row for row in self.state()['artifacts'] if row['path'] == name)

    def start(self):
        self.run_cli('init', '--brief', 'Synthetic gate fixture; no host integration claimed')
        self.write('layout.json', json.dumps(LAYOUT))

    def deliverable_pdf(self, name, note):
        self.board(name, note)
        self.run_cli('artifact', '--path', name, '--kind', 'pdf')
        self.run_cli('check', '--layout', 'layout.json', '--pdf', name)
        self.write('review-%s.md' % note, 'Fixture visual review: %s' % note)
        self.run_cli('review', '--kind', 'visual', '--evidence', 'review-%s.md' % note,
                     '--note', 'whole board and print crop', '--scope', 'whole_board',
                     '--scope', 'print')
        self.run_cli('decision', '--scope', 'delivery', '--text', 'accepted ' + note)


class ArtifactLifecycleTests(GateCase):
    def test_r2_replaces_r1_and_history_keeps_path_hash_and_revision(self):
        self.start()
        self.deliverable_pdf('boards-r1.pdf', 'R1')
        self.assertEqual(self.run_cli('deliver')['delivery'], 'accepted')
        old = self.artifact('boards-r1.pdf')
        self.assertEqual((old['status'], old['revision']), ('active', 'R1'))

        self.run_cli('checkpoint', '--revision', 'R2', '--stage', 'scheme', '--reason', 'entry changed')
        self.deliverable_pdf('boards-r2.pdf', 'R2')
        result = self.run_cli('deliver')
        self.assertEqual(result['delivery'], 'accepted')
        self.assertNotIn('Stale artifact revision: boards-r1.pdf', result.get('errors', []))
        self.assertEqual(result['active_artifacts'], ['boards-r2.pdf'])
        self.assertIn('boards-r1.pdf', result['superseded_artifacts'])

        replaced, current = self.artifact('boards-r1.pdf'), self.artifact('boards-r2.pdf')
        self.assertEqual(replaced['status'], 'superseded')
        self.assertEqual(replaced['superseded_reason'], 'revision_advanced')
        self.assertEqual(replaced['superseded_by'], current['id'])
        self.assertEqual(current['supersedes'], [replaced['id']])
        self.assertEqual(replaced['revision'], 'R1')
        self.assertEqual(len(replaced['sha256']), 64)
        self.assertTrue((self.base / 'boards-r1.pdf').is_file(), 'history must keep the old file')

    def test_declared_supersession_replaces_a_different_path_at_one_revision(self):
        self.start()
        self.deliverable_pdf('draft.pdf', 'draft')
        self.run_cli('artifact', '--path', 'draft.pdf', '--kind', 'pdf')
        self.write('final.pdf', 'placeholder')
        self.board('final.pdf', 'final')
        payload = self.run_cli('artifact', '--path', 'final.pdf', '--kind', 'pdf',
                               '--supersedes', 'draft.pdf')
        self.assertEqual([row['path'] for row in payload['superseded']], ['draft.pdf'])
        self.assertEqual(payload['superseded'][0]['reason'], 'superseded_by_declaration')
        self.assertEqual(self.artifact('draft.pdf')['status'], 'superseded')
        self.assertEqual(self.artifact('final.pdf')['status'], 'active')

    def test_unknown_supersede_target_is_refused_without_touching_state(self):
        self.start()
        self.deliverable_pdf('boards.pdf', 'only')
        self.run_cli('artifact', '--path', 'boards.pdf', '--kind', 'pdf',
                     '--supersedes', 'never-registered.pdf', ok=False)
        self.assertEqual(len(self.state()['artifacts']), 1)
        self.assertEqual(self.state()['artifacts'][0]['status'], 'active')

    def test_archived_artifact_leaves_the_gate_but_keeps_its_record(self):
        self.start()
        self.deliverable_pdf('boards.pdf', 'board')
        self.write('spots.pdf', 'spot drawing')
        self.run_cli('artifact', '--path', 'spots.pdf', '--kind', 'pdf')
        self.assertIn('spots.pdf', self.run_cli('status')['gate_summary']['active_artifacts'])
        archived = self.run_cli('archive', '--path', 'spots.pdf', '--reason', 'withdrawn by user')
        self.assertEqual(archived['status'], 'archived')
        self.assertEqual(archived['archive_reason'], 'withdrawn by user')
        self.assertTrue((self.base / 'spots.pdf').is_file())
        summary = self.run_cli('status')['gate_summary']
        self.assertEqual(summary['archived_artifacts'], ['spots.pdf'])
        self.assertEqual(summary['active_artifacts'], ['boards.pdf'])
        self.assertFalse(any('spots.pdf' in error for error in summary['errors']))
        self.run_cli('archive', '--path', 'spots.pdf', '--reason', 'again', ok=False)
        self.run_cli('archive', '--path', 'boards.pdf', '--reason', '  ', ok=False)

    def test_paths_stay_relative_and_posix_for_both_platforms(self):
        self.start()
        self.deliverable_pdf('boards.pdf', 'paths')
        for row in self.state()['artifacts']:
            self.assertFalse(os.path.isabs(row['path']))
            self.assertNotIn('\\', row['path'])
        for record in self.state()['validations']:
            self.assertNotIn('\\', record['evidence']['path'])
            self.assertFalse(os.path.isabs(record['evidence']['path']))


class DeliveryRequirementTests(GateCase):
    def test_pdf_requires_paper_layout_revision_and_both_visual_scopes(self):
        self.start()
        self.board('boards.pdf', 'R1')
        self.run_cli('artifact', '--path', 'boards.pdf', '--kind', 'pdf')
        self.run_cli('decision', '--scope', 'delivery', '--text', 'accepted')
        blocked = self.run_cli('deliver', ok=False)
        self.assertIn('Missing required validation: automatic_check', blocked['errors'])
        self.assertIn('Missing required validation: visual_whole_board for boards.pdf',
                      blocked['errors'])
        self.assertIn('Missing required validation: visual_print for boards.pdf', blocked['errors'])

        self.run_cli('check', '--layout', 'layout.json', '--pdf', 'boards.pdf')
        self.write('visual.md', 'reviewed whole board only')
        self.run_cli('review', '--kind', 'visual', '--evidence', 'visual.md',
                     '--note', 'whole board', '--scope', 'whole_board')
        still = self.run_cli('deliver', ok=False)
        self.assertEqual(still['errors'], ['Missing required validation: visual_print for boards.pdf'])
        self.write('print.md', 'reviewed print crop')
        self.run_cli('review', '--kind', 'visual', '--evidence', 'print.md',
                     '--note', 'print crop', '--scope', 'print')
        self.assertEqual(self.run_cli('deliver')['delivery'], 'accepted')

    def test_missing_required_host_validation_blocks_a_dwg_delivery(self):
        self.start()
        self.write('plan.dwg', 'dwg bytes')
        self.run_cli('artifact', '--path', 'plan.dwg', '--kind', 'dwg')
        self.run_cli('require', '--check', 'automatic_check', '--status', 'not_applicable',
                     '--reason', 'No PDF boards in this delivery')
        self.write('view.md', 'plan looked at')
        self.run_cli('review', '--kind', 'visual', '--evidence', 'view.md', '--note', 'plan sheet')
        self.run_cli('decision', '--scope', 'delivery', '--text', 'accepted')
        blocked = self.run_cli('deliver', ok=False)
        for name in ('cad_reopen', 'cad_layers', 'cad_dimensions', 'cad_editability'):
            self.assertIn('Missing required validation: %s for plan.dwg' % name, blocked['errors'])

    def test_not_applicable_host_checks_deliver_with_a_recorded_reason(self):
        self.start()
        self.write('plan.dwg', 'dwg bytes')
        self.run_cli('artifact', '--path', 'plan.dwg', '--kind', 'dwg')
        self.run_cli('require', '--check', 'automatic_check', '--status', 'not_applicable',
                     '--reason', 'No PDF boards in this delivery')
        self.run_cli('require', '--check', 'cad_layers', '--artifact', 'plan.dwg',
                     '--status', 'not_applicable', '--reason', 'Reference drawing without layers')
        self.write('cad.txt', 'CAD 2024 reopened, dimensions listed, editability confirmed')
        self.run_cli('review', '--kind', 'host', '--check', 'cad_reopen', '--artifact', 'plan.dwg',
                     '--evidence', 'cad.txt', '--note', 'reopen after save')
        self.run_cli('review', '--kind', 'host', '--check', 'cad_dimensions', '--artifact', 'plan.dwg',
                     '--evidence', 'cad.txt', '--note', 'dimensions read back')
        self.run_cli('review', '--kind', 'host', '--check', 'cad_editability', '--artifact', 'plan.dwg',
                     '--evidence', 'cad.txt', '--note', 'block edit test')
        self.write('view.md', 'plan sheet')
        self.run_cli('review', '--kind', 'visual', '--evidence', 'view.md', '--note', 'plan sheet')
        self.run_cli('decision', '--scope', 'delivery', '--text', 'accepted')
        result = self.run_cli('deliver')
        self.assertEqual(result['delivery'], 'accepted')
        waived = {row['check']: row for row in result['waived']}
        self.assertEqual(waived['cad_layers']['reason'], 'Reference drawing without layers')
        self.assertIn('automatic_check', waived)
        self.assertEqual([row['check'] for row in result['validated'] if row['target'] == 'plan.dwg'],
                         ['visual_whole_board', 'cad_reopen', 'cad_dimensions', 'cad_editability'])

    def test_waiver_without_reason_is_refused(self):
        self.start()
        self.run_cli('require', '--check', 'automatic_check', '--status', 'not_applicable',
                     '--reason', '   ', ok=False)

    def test_project_level_check_cannot_be_declared_per_artifact(self):
        self.start()
        self.write('plan.dwg', 'dwg bytes')
        self.run_cli('artifact', '--path', 'plan.dwg', '--kind', 'dwg')
        self.run_cli('require', '--check', 'automatic_check', '--artifact', 'plan.dwg', ok=False)
        self.run_cli('require', '--check', 'cad_layers', ok=False)

    def test_automatic_check_output_cannot_be_filed_as_host_evidence(self):
        self.start()
        self.board('boards.pdf', 'R1')
        self.run_cli('artifact', '--path', 'boards.pdf', '--kind', 'pdf')
        self.run_cli('check', '--layout', 'layout.json', '--pdf', 'boards.pdf')
        self.run_cli('review', '--kind', 'host', '--check', 'psd_layers', '--artifact', 'boards.pdf',
                     '--evidence', 'automatic-checks.json', '--note', 'pretend', ok=False)
        self.write('copy.json', (self.base / 'automatic-checks.json').read_text(encoding='utf-8'))
        self.run_cli('review', '--kind', 'host', '--check', 'psd_layers', '--artifact', 'boards.pdf',
                     '--evidence', 'copy.json', '--note', 'renamed copy', ok=False)
        self.assertFalse(any(row['lane'] == 'host' for row in self.state()['validations']))

    def test_host_check_must_match_the_artifact_kind(self):
        self.start()
        self.board('boards.pdf', 'R1')
        self.run_cli('artifact', '--path', 'boards.pdf', '--kind', 'pdf')
        self.write('cad.txt', 'not a CAD file')
        self.run_cli('review', '--kind', 'host', '--check', 'cad_reopen', '--artifact', 'boards.pdf',
                     '--evidence', 'cad.txt', '--note', 'wrong kind', ok=False)

    def test_negative_visual_conclusion_blocks_delivery(self):
        self.start()
        self.board('boards.pdf', 'R1')
        self.run_cli('artifact', '--path', 'boards.pdf', '--kind', 'pdf')
        self.run_cli('check', '--layout', 'layout.json', '--pdf', 'boards.pdf')
        self.write('visual.md', 'titles collide')
        self.run_cli('review', '--kind', 'visual', '--evidence', 'visual.md', '--note', 'rework',
                     '--scope', 'whole_board', '--scope', 'print', '--conclusion', 'needs_rework')
        self.run_cli('decision', '--scope', 'delivery', '--text', 'accepted')
        blocked = self.run_cli('deliver', ok=False)
        self.assertIn('Visual review requires rework: visual_whole_board for boards.pdf',
                      blocked['errors'])


class ReviewInvalidationTests(GateCase):
    def test_changed_artifact_invalidates_the_visual_review(self):
        self.start()
        self.deliverable_pdf('boards.pdf', 'R1')
        self.assertEqual(self.run_cli('deliver')['delivery'], 'accepted')
        self.board('boards.pdf', 'silently replaced drawing')
        blocked = self.run_cli('deliver', ok=False)
        self.assertIn('Artifact changed: boards.pdf', blocked['errors'])
        self.assertTrue(any('reviewed file changed on disk: boards.pdf' in error
                            for error in blocked['errors']), blocked['errors'])

    def test_reregistering_an_identical_file_still_invalidates_the_review(self):
        self.start()
        self.deliverable_pdf('boards.pdf', 'R1')
        self.assertEqual(self.run_cli('deliver')['delivery'], 'accepted')
        self.run_cli('artifact', '--path', 'boards.pdf', '--kind', 'pdf')
        blocked = self.run_cli('deliver', ok=False)
        self.assertTrue(any('artifact superseded' in error or 'artifact re-registered' in error
                            for error in blocked['errors']), blocked['errors'])

    def test_changed_artifact_invalidates_host_validation(self):
        self.start()
        self.write('model.rvt', 'revit bytes')
        self.run_cli('artifact', '--path', 'model.rvt', '--kind', 'rvt')
        self.run_cli('require', '--check', 'automatic_check', '--status', 'not_applicable',
                     '--reason', 'Model only')
        self.write('revit.txt', 'Revit 2024 reopened; 812 objects; no warnings')
        for check in ('revit_reopen', 'revit_objects', 'revit_model_state'):
            self.run_cli('review', '--kind', 'host', '--check', check, '--artifact', 'model.rvt',
                         '--evidence', 'revit.txt', '--note', 'saved and reopened')
        self.write('view.md', 'model screenshots')
        self.run_cli('review', '--kind', 'visual', '--evidence', 'view.md', '--note', 'screenshots')
        self.run_cli('decision', '--scope', 'delivery', '--text', 'accepted')
        self.assertEqual(self.run_cli('deliver')['delivery'], 'accepted')
        self.write('model.rvt', 'revit bytes after a silent edit')
        blocked = self.run_cli('deliver', ok=False)
        for check in ('revit_reopen', 'revit_objects', 'revit_model_state'):
            self.assertTrue(any(check in error and 'reviewed file changed on disk' in error
                                for error in blocked['errors']), (check, blocked['errors']))

    def test_one_review_can_bind_several_artifacts_and_any_change_invalidates_it(self):
        self.start()
        self.board('one.pdf', 'sheet one')
        self.board('two.pdf', 'sheet two')
        for name in ('one.pdf', 'two.pdf'):
            self.run_cli('artifact', '--path', name, '--kind', 'pdf')
        self.run_cli('check', '--layout', 'layout.json', '--pdf', 'one.pdf')
        self.write('cross.md', 'both sheets compared for consistency')
        self.run_cli('review', '--kind', 'visual', '--evidence', 'cross.md',
                     '--note', 'cross-drawing consistency', '--scope', 'whole_board',
                     '--scope', 'print', '--scope', 'cross_drawing',
                     '--artifact', 'one.pdf', '--artifact', 'two.pdf')
        record = self.state()['validations'][-1]
        self.assertEqual([row['path'] for row in record['artifacts']], ['one.pdf', 'two.pdf'])
        self.assertEqual(record['scopes'], ['whole_board', 'print', 'cross_drawing'])
        self.run_cli('decision', '--scope', 'delivery', '--text', 'accepted')
        self.assertEqual(self.run_cli('deliver')['delivery'], 'accepted')

        self.board('two.pdf', 'sheet two, silently reworked')
        blocked = self.run_cli('deliver', ok=False)
        self.assertTrue(any('visual_print for one.pdf' in error and
                            'reviewed file changed on disk: two.pdf' in error
                            for error in blocked['errors']), blocked['errors'])
        self.assertTrue(any('visual_whole_board for two.pdf' in error
                            for error in blocked['errors']), blocked['errors'])

    def test_review_target_must_be_an_active_artifact(self):
        self.start()
        self.board('boards.pdf', 'R1')
        self.run_cli('artifact', '--path', 'boards.pdf', '--kind', 'pdf')
        self.write('loose.md', 'review of something unregistered')
        self.write('notes.txt', 'not registered')
        self.run_cli('review', '--kind', 'visual', '--evidence', 'loose.md', '--note', 'stray',
                     '--artifact', 'notes.txt', ok=False)


class LegacyStateTests(GateCase):
    def legacy_project(self):
        digest = lambda name: hashlib.sha256((self.base / name).read_bytes()).hexdigest()
        self.board('boards.pdf', 'legacy board')
        self.write('layout.json', json.dumps(LAYOUT))
        self.write('visual.md', 'legacy review note')
        self.write('automatic-checks.json', json.dumps({'automatic_checks': 'passed'}))
        state = {'schema_version': 1, 'revision': 'R1', 'stage': 'scheme', 'brief': 'legacy',
                 'artifacts': [{'path': 'boards.pdf', 'sha256': digest('boards.pdf'),
                                'revision': 'R1', 'kind': 'pdf'}],
                 'decisions': [{'revision': 'R1', 'scope': 'delivery', 'user_text': 'accepted'}],
                 'reviews': {
                     'automatic': {'revision': 'R1', 'path': 'automatic-checks.json',
                                   'sha256': digest('automatic-checks.json'), 'passed': True,
                                   'inputs': {'layout.json': digest('layout.json'),
                                              'boards.pdf': digest('boards.pdf')}},
                     'visual': {'revision': 'R1', 'path': 'visual.md',
                                'sha256': digest('visual.md'), 'note': 'legacy note'}},
                 'history': []}
        (self.base / 'project.json').write_text(json.dumps(state, ensure_ascii=False, indent=2),
                                               encoding='utf-8')

    def test_schema_one_state_is_readable_and_still_delivers(self):
        self.legacy_project()
        view = self.run_cli('status')
        self.assertEqual(view['schema_version'], 2)
        self.assertEqual(len(view['validations']), 2)
        self.assertTrue(view['validations'][1]['legacy'])
        self.assertEqual(view['gate_summary']['errors'], [])
        result = self.run_cli('deliver')
        self.assertEqual(result['delivery'], 'accepted')
        self.assertTrue(all(row['legacy'] for row in result['validated']
                            if row['check'].startswith('visual_')))

    def test_legacy_review_is_invalidated_by_a_changed_artifact(self):
        self.legacy_project()
        self.board('boards.pdf', 'legacy board, edited later')
        blocked = self.run_cli('deliver', ok=False)
        self.assertTrue(any('reviewed file changed on disk' in error for error in blocked['errors']),
                        blocked['errors'])

    def test_legacy_host_note_cannot_satisfy_a_host_requirement(self):
        self.legacy_project()
        state = json.loads((self.base / 'project.json').read_text(encoding='utf-8'))
        state['artifacts'][0]['kind'] = 'dwg'
        (self.base / 'plan.dwg').write_text('dwg bytes', encoding='utf-8')
        state['artifacts'].append({'path': 'plan.dwg', 'sha256': hashlib.sha256(b'dwg bytes').hexdigest(),
                                   'revision': 'R1', 'kind': 'dwg'})
        state['reviews']['host'] = {'revision': 'R1', 'path': 'visual.md',
                                    'sha256': state['reviews']['visual']['sha256'],
                                    'note': 'reopened in CAD, I think'}
        (self.base / 'project.json').write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
        blocked = self.run_cli('deliver', ok=False)
        self.assertIn('Missing required validation: cad_reopen for plan.dwg', blocked['errors'])


if __name__ == '__main__':
    unittest.main()
