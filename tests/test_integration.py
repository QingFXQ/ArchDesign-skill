"""Real CLI integration and synthetic project-to-PDF delivery regression."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SKILL=ROOT/'skills/architecture-design-workflow'
SCRIPTS=SKILL/'scripts'
RAG=SKILL/'assets/knowledge/architecture-case-rag'
ENV=dict(os.environ,PYTHONUTF8='1',PYTHONIOENCODING='utf-8')


def cli(script,*args,cwd=None):
    return subprocess.run([sys.executable,'-X','utf8',str(script),*map(str,args)],cwd=cwd,env=ENV,
                          capture_output=True,text=True,encoding='utf-8',timeout=120)


class ResourceIntegrationTests(unittest.TestCase):
    def test_real_baseline_filters_corpus_and_returns_existing_sources(self):
        with tempfile.TemporaryDirectory(prefix='建筑 resource space ') as folder:
            cfg=Path(folder)/'resources.json'
            cfg.write_text(json.dumps({'design_case_root':str(RAG)}),encoding='utf-8')
            result=cli(SCRIPTS/'resources.py','design','--config',cfg,'--query','图书馆','--mode','lexical',cwd=folder)
            self.assertEqual(result.returncode,0,result.stderr)
            data=json.loads(result.stdout)
            self.assertEqual(data['actual_mode'],'baseline')
            self.assertTrue(data['results'])
            for row in data['results']:
                source=RAG/row['path']
                self.assertTrue(source.is_file())
                self.assertIn('图书馆',source.read_text(encoding='utf-8'))
            miss=cli(SCRIPTS/'resources.py','design','--config',cfg,'--query','zzzz_no_such_case_9384','--mode','lexical')
            self.assertEqual(json.loads(miss.stdout)['results'],[])

    def test_actual_backend_auto_fallback_and_explicit_semantic_failure(self):
        with tempfile.TemporaryDirectory(prefix='案例 space ') as folder:
            base=Path(folder);backend=base/'backend'
            shutil.copytree(RAG/'scripts',backend/'scripts',ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copytree(RAG/'cases',backend/'cases')
            (backend/'index').mkdir()
            shutil.copy2(RAG/'index/cases.json',backend/'index/cases.json')
            cfg=base/'config.json';cfg.write_text(json.dumps({'design_case_root':'backend'}),encoding='utf-8')
            before=hashlib.sha256((backend/'index/cases.json').read_bytes()).hexdigest()
            result=cli(SCRIPTS/'resources.py','design','--config',cfg,'--query','图书馆',cwd=base)
            self.assertEqual(result.returncode,0,result.stderr)
            data=json.loads(result.stdout)
            self.assertEqual(data['actual_mode'],'baseline');self.assertTrue(data['fallback_reasons'])
            self.assertTrue(data['results'])
            result=cli(SCRIPTS/'resources.py','design','--config',cfg,'--query','图书馆','--mode','semantic')
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(before,hashlib.sha256((backend/'index/cases.json').read_bytes()).hexdigest())
            self.assertFalse((backend/'index/semantic-sections.json').exists())

    def test_bundled_engineering_returns_real_method_evidence_and_missing_revit_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            cfg=Path(folder)/'empty.json';cfg.write_text('{}')
            result=cli(SCRIPTS/'resources.py','engineering','--config',cfg,'--query','Transaction','--software','revit')
            self.assertEqual(result.returncode,0,result.stderr)
            rows=json.loads(result.stdout)['results'];self.assertTrue(rows)
            self.assertTrue(all(Path(row['path']).is_file() and row['evidence'] for row in rows))
            result=cli(SCRIPTS/'resources.py','revit','--config',cfg,'--query','window','--revit','2021')
            self.assertEqual(result.returncode,2)
            self.assertIn('Missing resource binding',result.stderr)

    def test_tilde_config_and_relative_bindings_are_consistent_from_another_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            cfg=Path(folder)/'config.json';cfg.write_text(json.dumps({'design_case_root':str(RAG)}))
            # Use a real config under the user's home and remove it immediately.
            with tempfile.TemporaryDirectory(dir=Path.home()) as home_folder:
                config=Path(home_folder)/'resource.json';config.write_text(cfg.read_text())
                arg='~/'+config.relative_to(Path.home()).as_posix()
                result=cli(SCRIPTS/'resources.py','status','--config',arg,cwd=folder)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertTrue(json.loads(result.stdout)['design_case_root']['exists'])


class DeliveryIntegrationTests(unittest.TestCase):
    def test_real_retrieval_layout_pdf_checks_acceptance_and_invalidation(self):
        import pymupdf as fitz
        with tempfile.TemporaryDirectory(prefix='设计 project space ') as folder:
            base=Path(folder)
            def project(*args,ok=True):
                result=cli(SCRIPTS/'project.py','--root',base,*args,cwd=base)
                if ok:self.assertEqual(result.returncode,0,result.stderr+result.stdout)
                else:self.assertNotEqual(result.returncode,0)
                return json.loads(result.stdout or result.stderr)
            project('init','--brief','Synthetic library; no host integration claimed')
            project('init','--brief','Cannot overwrite',ok=False)
            (base/'resources.json').write_text(json.dumps({'design_case_root':str(RAG)}),encoding='utf-8')
            retrieval=cli(SCRIPTS/'resources.py','design','--config',base/'resources.json','--query','图书馆','--mode','lexical')
            self.assertEqual(retrieval.returncode,0,retrieval.stderr)
            (base/'research.json').write_text(retrieval.stdout,encoding='utf-8')
            for stage in ['concept','scheme','production','visualization','presentation']:
                project('checkpoint','--revision','R1','--stage',stage,'--reason','Synthetic fixture progress')
            doc=fitz.open();page=doc.new_page(width=594*72/25.4,height=841*72/25.4)
            page.draw_rect(fitz.Rect(30,30,500,500));page.insert_text((40,60),'Synthetic plan R1')
            doc.save(base/'boards.pdf');doc.close()
            layout={'paper_mm':[594,841],'expected_revision':'R1','required_items':['plan'],
                    'pages':[{'items':[{'id':'plan','revision':'R1','rect_mm':[10,10,200,200],
                     'source_frame_mm':[200,200],'source_scale':200,'claimed_scale':200,'source':'boards.pdf'}]}]}
            (base/'layout.json').write_text(json.dumps(layout))
            (base/'visual.md').write_text('Synthetic fixture review only; host production unverified.')
            for file in ['boards.pdf','research.json']:
                project('artifact','--path',file,'--kind','synthetic-fixture')
            project('check','--layout','layout.json','--pdf','boards.pdf')
            project('deliver',ok=False)
            project('review','--kind','visual','--evidence','visual.md','--note','Fixture assertion only')
            project('decision','--scope','delivery','--text','Synthetic test acceptance')
            self.assertEqual(project('deliver')['delivery'],'accepted')
            # A scale error in the checked input invalidates approval even if the PDF is unchanged.
            layout['pages'][0]['items'][0]['claimed_scale']=100
            (base/'layout.json').write_text(json.dumps(layout))
            result=project('deliver',ok=False);self.assertTrue(any('input changed' in e for e in result['errors']))
            project('check','--layout','layout.json','--pdf','boards.pdf',ok=False)
            project('deliver',ok=False)
            project('checkpoint','--revision','R2','--stage','scheme','--reason','Changed scheme')
            result=project('deliver',ok=False)
            self.assertTrue(any('Stale artifact' in e for e in result['errors']))
            self.assertTrue(any('user delivery decision' in e for e in result['errors']))
            outside=base.parent/'outside-unavailable.rvt'
            project('artifact','--path',outside,'--kind','source',ok=False)


if __name__=='__main__':
    unittest.main()
