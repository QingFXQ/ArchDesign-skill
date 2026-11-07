"""Audit local references, preserved assets and obsolete execution terms."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
from urllib.parse import unquote,urlsplit

ROOT=Path(__file__).resolve().parents[1]
SKILL=ROOT/'skills/architecture-design-workflow'
HISTORY=SKILL/'assets/history'
CORPUS=SKILL/'assets/knowledge/architecture-case-rag'
LEGACY=re.compile(r'multica|\bdirector\b|\bhandoff\b|六角色|任务路由|多智能体|多角色|角色交接',re.I)


def audit():
    paths=[p for p in ROOT.rglob('*') if p.is_file() and not any(part in ('.git','.codegraph','__pycache__','.venv') for part in p.relative_to(ROOT).parts)]
    broken=[];legacy=[];urls=set();preservation=[]
    for path in paths:
        if path.suffix.lower() not in ('.md','.py','.json','.yaml','.yml','.txt','.csv','.js','.svg'):continue
        if path.name in ('repository-check.json','external-links.json') and path.parent == ROOT/'audit':continue
        try:text=path.read_text(encoding='utf-8-sig')
        except UnicodeError:continue
        category='history' if path.is_relative_to(HISTORY) else 'source-data' if path.is_relative_to(CORPUS/'cases') or path.is_relative_to(CORPUS/'index') or path.is_relative_to(CORPUS/'sources') else 'audit' if path.is_relative_to(ROOT/'audit') or path==Path(__file__).resolve() else 'active'
        for number,line in enumerate(text.splitlines(),1):
            if LEGACY.search(line):legacy.append({'file':path.relative_to(ROOT).as_posix(),'line':number,'category':category,'text':line[:220]})
        if category != 'audit':
            urls.update(u.rstrip('.,;:，。；：') for u in re.findall(r'https?://[^\s\"<>`)]+',text))
        if path.suffix=='.md':
            for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',text):
                target=target.strip('<>');parsed=urlsplit(target)
                if parsed.scheme in ('https','http'):
                    urls.add(target);continue
                if parsed.scheme or not parsed.path:continue
                dest=(path.parent/unquote(parsed.path)).resolve()
                if not dest.exists():broken.append({'file':path.relative_to(ROOT).as_posix(),'target':target,'category':category})
    manifest_path=ROOT/'audit/migration.json'
    preservation=[];preservation_checked=False
    if manifest_path.is_file():
        preservation_checked=True
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        for row in manifest['files']:
            target=row['target']
            if target and (target.startswith('skills/architecture-design-workflow/assets/history/') or row['path'].startswith('knowledge/architecture-case-rag/cases/') or row['path'].startswith('knowledge/architecture-case-rag/index/')):
                path=ROOT/target
                # LFS checkout materializes bytes; baseline captures those same materialized bytes.
                data=path.read_bytes() if path.is_file() else b''
                expected=row.get('portable_sha256',row['sha256'])
                if row.get('portable_sha256'):
                    data=data.replace(b'\r\n',b'\n')
                if not path.is_file() or hashlib.sha256(data).hexdigest()!=expected:
                    preservation.append(target)
    skills=[p.relative_to(ROOT).as_posix() for p in paths if p.name=='SKILL.md']
    index=json.loads((CORPUS/'index/cases.json').read_text(encoding='utf-8'))
    records=index.get('cases',[]) if isinstance(index,dict) else index
    corpus_errors=[str(row.get('path')) for row in records if not (CORPUS/row.get('path','')).is_file()]
    errors=[row for row in broken+legacy if row['category']=='active']
    errors+=preservation+corpus_errors
    if skills!=['skills/architecture-design-workflow/SKILL.md']:errors.append({'skill_entries':skills})
    return {'skill_entries':skills,'files_scanned':len(paths),'broken_local_links':broken,'legacy_matches':legacy,
            'preservation_checked':preservation_checked,'preservation_errors':preservation,
            'corpus_path_errors':corpus_errors,'external_urls':sorted(urls),'errors':errors}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');parser.add_argument('--report')
    args=parser.parse_args();report=audit()
    if args.report:
        (ROOT/args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:report[key] for key in ['skill_entries','files_scanned','preservation_checked','preservation_errors','errors']},ensure_ascii=False,indent=2))
    print(f"Historical/source/audit matches: {len(report['legacy_matches'])}; broken local links (all categories): {len(report['broken_local_links'])}; external URLs: {len(report['external_urls'])}")
    return 1 if report['errors'] else 0


if __name__=='__main__':raise SystemExit(main())
