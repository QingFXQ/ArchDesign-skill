"""Package integrity checks verify real files, corpus references and evidence preservation."""
from pathlib import Path
import importlib.util
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('repository_audit',ROOT/'scripts/audit_repository.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
HISTORY=ROOT/'skills/architecture-design-workflow/assets/history'

class PackageIntegrityTests(unittest.TestCase):
    def test_single_entry_current_links_and_case_paths(self):
        report=audit.audit()
        self.assertEqual(report['skill_entries'],['skills/architecture-design-workflow/SKILL.md'])
        self.assertEqual(report['errors'],[])
        self.assertEqual(report['corpus_path_errors'],[])

    def test_historical_evidence_and_case_corpus_remain_content_identical(self):
        report=audit.audit()
        self.assertEqual(report['preservation_errors'],[])
        # The public release ships without the private history archive and its
        # migration manifest; only the development checkout can prove preservation.
        if HISTORY.is_dir():
            self.assertTrue(report['preservation_checked'])
            self.assertTrue(any(row['category']=='history' for row in report['broken_local_links']))

if __name__=='__main__':unittest.main()
