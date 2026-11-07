"""Read-only access to existing design, engineering-method and native Revit libraries."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


SKILL_ROOT = Path(__file__).resolve().parents[1]


def bindings(explicit=None):
    home = Path(os.environ.get('CODEX_HOME') or Path.home()/'.codex').expanduser()
    path = Path(explicit).expanduser().resolve() if explicit else home/'architecture-resources.json'
    config = json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else {}
    if explicit and not path.is_file():
        raise ValueError(f'Resource config unavailable: {path}')
    if not isinstance(config, dict):
        raise ValueError('Resource config must be a JSON object')
    for key, value in config.items():
        if value is not None:
            if not isinstance(value, str):
                raise ValueError(f'Resource path must be a string: {key}')
            expanded = Path(value).expanduser()
            config[key] = str((expanded if expanded.is_absolute() else path.parent/expanded).resolve())
    config.setdefault('design_case_root', str(SKILL_ROOT/'assets/knowledge/architecture-case-rag'))
    return config


def existing(config, key, directory=False):
    value = config.get(key)
    if not value:
        raise ValueError(f'Missing resource binding: {key}')
    path = Path(value).expanduser().resolve()
    if not (path.is_dir() if directory else path.is_file()):
        raise ValueError(f'Resource unavailable: {key}: {path}')
    return path


def command(config, kind, query, limit=3, mode='auto', software='all', revit=None, asset_kind=None):
    if not query.strip() or limit < 1:
        raise ValueError('Provide a nonempty query and positive limit')
    py = [sys.executable, '-X', 'utf8']
    if kind == 'design':
        root = existing(config, 'design_case_root', directory=True)
        script = root/'scripts/search_cases.py'
        if not (root/'index/cases.json').is_file():
            raise ValueError('Design index unavailable; do not rebuild automatically')
        if mode not in ('auto', 'lexical', 'semantic', 'hybrid'):
            raise ValueError('Unknown design search mode')
        actual = 'baseline' if mode == 'lexical' else 'semantic' if mode == 'auto' else mode
        args = ['--query',query,'--mode',actual,'--max',str(limit),'--format','json']
        if actual == 'baseline':
            args = ['--mode','baseline','--max',str(limit),'--format','json','--keyword',*query.split()]
    elif kind == 'engineering':
        repo = existing(config, 'workflow_repo', directory=True)
        catalog = existing(config, 'engineering_catalog')
        if catalog != (repo/'knowledge/engineering-assets/catalog.json').resolve():
            raise ValueError('Configured catalog differs from backend catalog; configure matching workflow_repo')
        script = repo/'tools/engineering_assets/find_asset.py'
        args = ['--task',query,'--software',software,'--limit',str(limit),'--json']
    elif kind == 'revit':
        repo = existing(config, 'workflow_repo', directory=True)
        db = existing(config, 'revit_database')
        root = db.parent.parent
        if db != root/'database/revit-assets.sqlite':
            raise ValueError('Revit backend expects root/database/revit-assets.sqlite')
        if not isinstance(revit, int) or revit < 2000:
            raise ValueError('Supply actual host year with --revit')
        script = repo/'tools/revit_assets/library.py'
        args = ['--root',str(root),'search',query,'--revit',str(revit),'--limit',str(limit)]
        if asset_kind:
            args += ['--kind',asset_kind]
    else:
        raise ValueError('Unknown library kind')
    if not script.is_file():
        raise ValueError('Existing library tool unavailable: '+str(script))
    return py+[str(script)]+args


def status(config):
    keys = ['design_case_root','workflow_repo','engineering_catalog','revit_database','layout_catalog']
    return {k:{'path':config.get(k), 'optional':k != 'design_case_root',
               'exists':Path(config[k]).expanduser().exists() if config.get(k) else False}
            for k in keys}


def engineering_search(query, limit, software):
    if not query.strip() or limit < 1:
        raise ValueError('Provide a nonempty query and positive limit')
    terms = query.casefold().split()
    rows = []
    for path in (SKILL_ROOT/'references').rglob('*.md'):
        text = path.read_text(encoding='utf-8-sig')
        if software != 'all' and software not in (str(path) + text).casefold():
            continue
        lines = [line for line in text.splitlines() if any(t in line.casefold() for t in terms)]
        if lines:
            rows.append({'path':str(path), 'matches':len(lines), 'evidence':lines[:3]})
    return sorted(rows, key=lambda row:(-row['matches'], row['path']))[:limit]


def run_search(config, kind, query, limit=3, mode='auto', software='all', revit=None, asset_kind=None):
    if kind == 'engineering' and not config.get('engineering_catalog'):
        return {'requested_mode':'lexical', 'actual_mode':'lexical',
                'backend':'bundled-methods', 'results':engineering_search(query,limit,software)}
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    attempts = ['semantic','lexical'] if kind == 'design' and mode == 'auto' else [mode]
    failures = []
    for attempt in attempts:
        cmd = command(config,kind,query,limit,attempt,software,revit,asset_kind)
        try:
            result = subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',
                                    env=env,timeout=90,shell=False)
            if result.returncode:
                raise ValueError(result.stderr.strip() or f'Backend exited {result.returncode}')
            payload = json.loads(result.stdout)
            return {'requested_mode':mode, 'actual_mode':'baseline' if attempt == 'lexical' else attempt,
                    'fallback_reasons':failures, 'results':payload}
        except (subprocess.TimeoutExpired, ValueError) as exc:
            failures.append(str(exc))
            if attempt == attempts[-1]:
                raise ValueError('; '.join(failures)) from exc


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('kind', choices=['status','design','engineering','revit'])
    p.add_argument('--config')
    p.add_argument('--query', default='')
    p.add_argument('--limit', type=int, default=3)
    p.add_argument('--mode', choices=['auto','lexical','semantic','hybrid'], default='auto')
    p.add_argument('--software', choices=['all','revit','cad'], default='all')
    p.add_argument('--revit', type=int)
    p.add_argument('--asset-kind',choices=['family','family_template','project_template','project'])
    args = p.parse_args()
    try:
        config = bindings(args.config)
        if args.kind == 'status':
            r = status(config)
            print(json.dumps(r, ensure_ascii=False, indent=2))
            return 0 if all(v['exists'] for v in r.values() if not v['optional']) else 2
        result = run_search(config,args.kind,args.query,args.limit,args.mode,args.software,args.revit,args.asset_kind)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'error':str(exc),'result':'not verified; no library rebuilt'},ensure_ascii=False),file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
