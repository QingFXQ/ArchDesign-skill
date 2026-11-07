"""Project feedback records, similar-issue retrieval and reviewed lesson write-back."""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import re
import sys

SCHEMA_VERSION = 1
OPEN_STATUSES = ('reported', 'reproduced', 'diagnosed', 'fixed', 'pending')
CLOSED_STATUSES = ('regression_verified', 'project_specific', 'rejected')
STATUSES = OPEN_STATUSES + CLOSED_STATUSES
ROOT_CAUSE_STATUSES = ('confirmed', 'suspected', 'unknown')
LESSON_STATUSES = ('pending_validation', 'validated', 'applied', 'rejected')
LESSON_TARGETS = ('tool', 'process', 'skill_section')
COMMIT_PATTERN = re.compile(r'^[0-9a-f]{7,40}$')
SKILL_ROOT = Path(__file__).resolve().parents[1]

FIELD_WEIGHTS = (('tags', 3.0), ('category', 2.0), ('user_text', 1.2), ('expected', 1.2),
                 ('actual', 1.2), ('root_cause.text', 1.0), ('fix.summary', 0.8))
LATIN = re.compile(r'[a-z0-9_]+')
CJK = re.compile(r'[\u4e00-\u9fff]+')


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_file(root, value):
    path = (root / Path(value).expanduser()).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Feedback evidence must stay inside the project directory')
    if not path.is_file():
        raise ValueError(f'Evidence missing: {path}')
    return path


def rel(root, path):
    return path.relative_to(root).as_posix()


def save(path, state):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def field(record, dotted):
    value = record
    for part in dotted.split('.'):
        if not isinstance(value, dict):
            return ''
        value = value.get(part, '')
    return value if isinstance(value, str) else ' '.join(map(str, value or []))


def tokens(text):
    text = (text or '').lower()
    out = set(LATIN.findall(text))
    for run in CJK.findall(text):
        if len(run) == 1:
            out.add(run)
        else:
            out.update(run[i:i + 2] for i in range(len(run) - 1))
    return out


def text_matches(record, query):
    """Weighted keyword score over structured fields; no vector store and no model call."""
    wanted = tokens(query)
    if not wanted:
        return 0.0, []
    score, hits = 0.0, set()
    for dotted, weight in FIELD_WEIGHTS:
        shared = wanted & tokens(field(record, dotted))
        if shared:
            score += weight * len(shared) / len(wanted)
            hits |= shared
    if query.strip().lower() and query.strip().lower() in [str(t).lower() for t in record.get('tags', [])]:
        score += 1.0
    return score, sorted(hits)


def similar(records, query, limit=5, exclude=None, keep=None):
    rows = []
    for record in records:
        if exclude and record['id'] == exclude:
            continue
        if keep and not keep(record):
            continue
        score, hits = text_matches(record, query)
        if score > 0:
            rows.append({'id': record['id'], 'status': record['status'], 'score': round(score, 3),
                         'matched': hits, 'user_text': record['user_text'],
                         'root_cause': record['root_cause']['status'],
                         'fix': record['fix']['summary'],
                         'regression_tests': record['regression']['tests']})
    rows.sort(key=lambda row: (-row['score'], row['id']))
    return rows[:limit]


def load(root):
    path = root / 'feedback.json'
    if not path.exists():
        return {'schema_version': SCHEMA_VERSION, 'project': root.name, 'sequence': 0,
                'feedback': [], 'lessons': []}
    state = json.loads(path.read_text(encoding='utf-8-sig'))
    if state.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('Unsupported feedback schema')
    state.setdefault('feedback', [])
    state.setdefault('lessons', [])
    state.setdefault('sequence', len(state['feedback']))
    return state


def find(state, key, prefix):
    rows = state['lessons'] if prefix == 'L' else state['feedback']
    for record in rows:
        if record['id'] == key:
            return record
    raise ValueError(f'Unknown record: {key}')


def next_id(state, prefix):
    highest = 0
    for row in state['feedback'] + state['lessons']:
        if row['id'].startswith(prefix + '-'):
            try:
                highest = max(highest, int(row['id'].split('-')[1]))
            except ValueError:
                continue
    state['sequence'] = max(state.get('sequence', 0), highest)
    return f'{prefix}-{highest + 1:04d}'


def touch(record, status, note):
    record['history'].append({'from': record.get('status'), 'to': status, 'note': note, 'at': now()})
    record['status'] = status


def bind_files(root, values, label='artifact'):
    rows = []
    for value in values or []:
        path = local_file(root, value)
        rows.append({'path': rel(root, path), 'sha256': digest(path)})
    return rows


def project_revision(root):
    path = root / 'project.json'
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding='utf-8-sig')).get('revision', 'none')
        except ValueError:
            return 'none'
    return 'none'


def require_open(record, allowed, action):
    if record['status'] not in allowed:
        raise ValueError(f'{action} needs status in {allowed}; {record["id"]} is {record["status"]}')


def new_record(state, *, project, revision, user_text, expected, actual, category='',
               tags=None, steps=None, artifacts=None, evidence=None, source='manual',
               note='reported', extra=None, root_cause_status='unknown', root_cause=''):
    """One constructor for manual reports and collected events, so both share one lifecycle."""
    record = {'id': next_id(state, 'FB'), 'project': project, 'revision': revision,
              'status': 'reported', 'category': category,
              'tags': list(dict.fromkeys(tags or [])),
              'user_text': user_text, 'expected': expected, 'actual': actual,
              'steps': list(steps or []), 'artifacts': artifacts or [],
              'evidence': evidence or [],
              'root_cause': {'status': root_cause_status, 'text': root_cause,
                             'evidence': []},
              'fix': {'summary': '', 'commit': '', 'files': [], 'regression_tests': []},
              'regression': {'tests': [], 'result': 'not_run', 'evidence': []},
              'verification': {'result': 'not_run', 'evidence': []},
              'duplicate_of': None, 'reason': '', 'source': source,
              'history': [{'from': None, 'to': 'reported', 'note': note, 'at': now()}]}
    if extra:
        record.update(extra)
    state['feedback'].append(record)
    return record


def record_report(root, state, args):
    if args.root_cause_status == 'confirmed':
        raise ValueError('A root cause is confirmed through diagnose with evidence, not at report time')
    if not args.user_text.strip() or not args.expected.strip() or not args.actual.strip():
        raise ValueError('user_text, expected and actual are required')
    return new_record(state, project=args.project or state['project'],
                      revision=args.revision or project_revision(root),
                      user_text=args.user_text, expected=args.expected, actual=args.actual,
                      category=args.category, tags=args.tag, steps=args.step,
                      artifacts=bind_files(root, args.artifact),
                      evidence=bind_files(root, args.evidence),
                      note=args.note or 'reported',
                      root_cause_status=args.root_cause_status,
                      root_cause=args.root_cause)


def action_diagnose(root, record, args):
    require_open(record, ('reproduced', 'pending'), 'diagnose')
    if args.root_cause_status == 'confirmed':
        if not args.root_cause.strip():
            raise ValueError('A confirmed root cause needs a written explanation')
        evidence = bind_files(root, args.evidence)
        if not evidence:
            raise ValueError('A confirmed root cause needs evidence recorded with --evidence')
        record['root_cause'] = {'status': 'confirmed', 'text': args.root_cause,
                                'evidence': evidence}
    else:
        record['root_cause'] = {'status': args.root_cause_status, 'text': args.root_cause,
                                'evidence': bind_files(root, args.evidence)}
    touch(record, 'diagnosed', args.note or f'root cause {args.root_cause_status}')


def action_fix(root, record, args):
    require_open(record, ('diagnosed', 'pending'), 'fix')
    if not args.summary.strip():
        raise ValueError('A fix needs a summary')
    commit = (args.commit or '').strip().lower()
    if commit and not COMMIT_PATTERN.match(commit):
        raise ValueError('--commit must be a hexadecimal revision between 7 and 40 characters')
    record['fix'] = {'summary': args.summary, 'commit': commit,
                     'files': list(dict.fromkeys(args.file or [])),
                     'regression_tests': list(dict.fromkeys(args.regression_test or []))}
    touch(record, 'fixed', args.note or 'fix recorded')


def action_verify(root, record, args):
    require_open(record, ('fixed',), 'verify')
    tests = list(dict.fromkeys((record['fix'].get('regression_tests') or [])
                               + list(args.regression_test or [])))
    evidence = bind_files(root, args.evidence)
    record['regression'] = {'tests': tests, 'result': args.result, 'evidence': evidence}
    record['verification'] = {'result': args.result, 'evidence': evidence}
    if args.result != 'passed':
        record['history'].append({'from': 'fixed', 'to': 'fixed',
                                  'note': args.note or 'regression tests failed; fix unresolved',
                                  'at': now()})
        return
    if not tests:
        raise ValueError('A verified fix needs at least one regression test reference')
    touch(record, 'regression_verified', args.note or 'regression tests passed')


def action_mark(record, args):
    if not args.reason.strip():
        raise ValueError('pending, project_specific and rejected all need a recorded reason')
    if args.status == record['status']:
        return
    record['reason'] = args.reason
    touch(record, args.status, args.reason)


def action_lesson(root, state, args):
    if args.lesson_action == 'candidate':
        sources = []
        for key in args.source:
            record = find(state, key, 'FB')
            if record['status'] != 'regression_verified':
                raise ValueError(f'{record["id"]} is not regression_verified; '
                                 'a lesson needs verified evidence')
            sources.append(record['id'])
        if not sources:
            raise ValueError('A lesson needs at least one --source feedback id')
        if not args.text.strip():
            raise ValueError('A lesson needs a written statement')
        if args.target not in LESSON_TARGETS:
            raise ValueError('--target must be one of: ' + ', '.join(LESSON_TARGETS))
        record = {'id': next_id(state, 'L'), 'status': 'pending_validation',
                  'target': args.target, 'text': args.text, 'document': args.document or '',
                  'source_feedback': sources, 'evidence': bind_files(root, args.evidence),
                  'reviewed_by': None, 'reviewed_at': None, 'commit': None, 'reason': '',
                  'history': [{'from': None, 'to': 'pending_validation',
                               'note': args.note or 'candidate recorded', 'at': now()}]}
        state['lessons'].append(record)
        return record
    record = find(state, args.id, 'L')
    if args.lesson_action == 'validate':
        if record['status'] != 'pending_validation':
            raise ValueError(f'validate needs pending_validation; {record["id"]} is {record["status"]}')
        if not args.reviewed_by.strip():
            raise ValueError('A lesson becomes valid only through a named human review')
        evidence = bind_files(root, args.evidence) or record['evidence']
        if not evidence:
            raise ValueError('A lesson needs evidence before it can be validated')
        for key in record['source_feedback']:
            if find(state, key, 'FB')['status'] != 'regression_verified':
                raise ValueError(f'source {key} is not regression_verified')
        record.update(status='validated', evidence=evidence, reviewed_by=args.reviewed_by,
                      reviewed_at=now())
        record['history'].append({'from': 'pending_validation', 'to': 'validated',
                                  'note': args.note or 'reviewed by ' + args.reviewed_by, 'at': now()})
        return record
    if args.lesson_action == 'apply':
        if record['status'] != 'validated':
            raise ValueError(f'apply needs validated; {record["id"]} is {record["status"]}')
        document = (root / Path(args.document)).resolve() if Path(args.document).is_absolute() \
            else (SKILL_ROOT / args.document).resolve()
        if not document.is_relative_to(SKILL_ROOT):
            raise ValueError('A general lesson may only be applied inside this skill')
        if not document.is_file():
            raise ValueError(f'Target document missing: {document}')
        if not COMMIT_PATTERN.match(args.commit or ''):
            raise ValueError('--commit must be the hexadecimal revision carrying the document change')
        record.update(status='applied', document=rel(SKILL_ROOT, document),
                      commit=args.commit, reason=args.note or '')
        record['history'].append({'from': 'validated', 'to': 'applied',
                                  'note': args.note or 'applied to ' + record['document'],
                                  'at': now()})
        return record
    if args.lesson_action == 'reject':
        if not args.note.strip():
            raise ValueError('A rejection needs a recorded reason')
        if record['status'] in ('applied', 'rejected'):
            raise ValueError(f'{record["id"]} is already {record["status"]}')
        previous = record['status']
        record.update(status='rejected', reason=args.note)
        record['history'].append({'from': previous, 'to': 'rejected', 'note': args.note, 'at': now()})
        return record
    raise ValueError('Unknown lesson action')


def execute(args):
    root = Path(args.root).expanduser().resolve()
    path = root / 'feedback.json'
    if args.action == 'search':
        state = load(root)
        def keep(record):
            if args.category and record['category'] != args.category:
                return False
            return not args.tag or args.tag in record['tags']
        return {'query': args.query, 'results': similar(state['feedback'], args.query,
                                                         args.limit, keep=keep)}
    if args.action == 'status':
        state = load(root)
        counts = {name: 0 for name in STATUSES}
        for record in state['feedback']:
            counts[record['status']] = counts.get(record['status'], 0) + 1
        lessons = {name: 0 for name in LESSON_STATUSES}
        for record in state['lessons']:
            lessons[record['status']] = lessons.get(record['status'], 0) + 1
        return {'project': state['project'], 'feedback': len(state['feedback']),
                'open': sum(counts[name] for name in OPEN_STATUSES), 'by_status': counts,
                'lessons': len(state['lessons']), 'lessons_by_status': lessons}
    state = load(root)
    root.mkdir(parents=True, exist_ok=True)
    if args.action == 'report':
        record = record_report(root, state, args)
        save(path, state)
        query = ' '.join([record['user_text'], record['category'], ' '.join(record['tags'])])
        return {'feedback': record, 'similar': similar(state['feedback'], query, 3, record['id'])}
    if args.action == 'list':
        rows = [r for r in state['feedback']
                if (not args.status or r['status'] == args.status)
                and (not args.revision or r['revision'] == args.revision)]
        return {'feedback': [{'id': r['id'], 'status': r['status'], 'revision': r['revision'],
                             'category': r['category'], 'user_text': r['user_text'],
                             'root_cause': r['root_cause']['status']} for r in rows]}
    if args.action == 'reproduce':
        record = find(state, args.id, 'FB')
        require_open(record, ('reported', 'pending'), 'reproduce')
        if args.step:
            record['steps'] = list(dict.fromkeys(record['steps'] + list(args.step)))
        if args.evidence:
            record['evidence'] = record['evidence'] + bind_files(root, args.evidence)
        touch(record, 'reproduced', args.note or 'reproduced')
    elif args.action == 'diagnose':
        action_diagnose(root, find(state, args.id, 'FB'), args)
    elif args.action == 'fix':
        action_fix(root, find(state, args.id, 'FB'), args)
    elif args.action == 'verify':
        action_verify(root, find(state, args.id, 'FB'), args)
    elif args.action == 'mark':
        action_mark(find(state, args.id, 'FB'), args)
    elif args.action == 'link':
        record = find(state, args.id, 'FB')
        other = find(state, args.duplicate_of, 'FB')
        if record['id'] == other['id']:
            raise ValueError('A record cannot duplicate itself')
        record['duplicate_of'] = other['id']
        record['history'].append({'from': record['status'], 'to': record['status'],
                                  'note': 'linked to ' + other['id'], 'at': now()})
        return {'feedback': record}
    elif args.action == 'show':
        record = find(state, args.id, 'FB')
        return {'feedback': record,
                'similar': similar(state['feedback'], record['user_text'], 3, record['id'])}
    elif args.action == 'lesson':
        record = action_lesson(root, state, args)
        save(path, state)
        return {'lesson': record}
    save(path, state)
    return find(state, args.id, 'FB')


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', required=True)
    sub = p.add_subparsers(dest='action', required=True)
    q = sub.add_parser('report')
    q.add_argument('--user-text', required=True)
    q.add_argument('--expected', required=True)
    q.add_argument('--actual', required=True)
    q.add_argument('--revision')
    q.add_argument('--project')
    q.add_argument('--category', default='')
    q.add_argument('--tag', action='append', default=[])
    q.add_argument('--step', action='append', default=[])
    q.add_argument('--artifact', action='append', default=[])
    q.add_argument('--evidence', action='append', default=[])
    q.add_argument('--root-cause-status', choices=list(ROOT_CAUSE_STATUSES), default='unknown')
    q.add_argument('--root-cause', default='')
    q.add_argument('--note')
    q = sub.add_parser('reproduce')
    q.add_argument('--id', required=True)
    q.add_argument('--step', action='append', default=[])
    q.add_argument('--evidence', action='append', default=[])
    q.add_argument('--note')
    q = sub.add_parser('diagnose')
    q.add_argument('--id', required=True)
    q.add_argument('--root-cause-status', choices=list(ROOT_CAUSE_STATUSES), required=True)
    q.add_argument('--root-cause', default='')
    q.add_argument('--evidence', action='append', default=[])
    q.add_argument('--note')
    q = sub.add_parser('fix')
    q.add_argument('--id', required=True)
    q.add_argument('--summary', required=True)
    q.add_argument('--commit', default='')
    q.add_argument('--file', action='append', default=[])
    q.add_argument('--regression-test', action='append', default=[])
    q.add_argument('--note')
    q = sub.add_parser('verify')
    q.add_argument('--id', required=True)
    q.add_argument('--result', choices=['passed', 'failed'], required=True)
    q.add_argument('--evidence', action='append', default=[])
    q.add_argument('--regression-test', action='append', default=[])
    q.add_argument('--note')
    q = sub.add_parser('mark')
    q.add_argument('--id', required=True)
    q.add_argument('--status', choices=['pending', 'project_specific', 'rejected'], required=True)
    q.add_argument('--reason', default='')
    q = sub.add_parser('link')
    q.add_argument('--id', required=True)
    q.add_argument('--duplicate-of', required=True)
    q = sub.add_parser('show')
    q.add_argument('--id', required=True)
    q = sub.add_parser('list')
    q.add_argument('--status', choices=list(STATUSES))
    q.add_argument('--revision')
    q = sub.add_parser('search')
    q.add_argument('--query', required=True)
    q.add_argument('--category')
    q.add_argument('--tag')
    q.add_argument('--limit', type=int, default=5)
    q = sub.add_parser('lesson')
    ls = q.add_subparsers(dest='lesson_action', required=True)
    r = ls.add_parser('candidate')
    r.add_argument('--source', action='append', required=True)
    r.add_argument('--target', choices=list(LESSON_TARGETS), required=True)
    r.add_argument('--text', required=True)
    r.add_argument('--document', default='')
    r.add_argument('--evidence', action='append', default=[])
    r.add_argument('--note')
    r = ls.add_parser('validate')
    r.add_argument('--id', required=True)
    r.add_argument('--reviewed-by', required=True)
    r.add_argument('--evidence', action='append', default=[])
    r.add_argument('--note')
    r = ls.add_parser('apply')
    r.add_argument('--id', required=True)
    r.add_argument('--document', required=True)
    r.add_argument('--commit', required=True)
    r.add_argument('--note')
    r = ls.add_parser('reject')
    r.add_argument('--id', required=True)
    r.add_argument('--note', required=True)
    ls.add_parser('list')
    r = ls.add_parser('show')
    r.add_argument('--id', required=True)
    sub.add_parser('status')
    return p


def main():
    args = parser().parse_args()
    try:
        if args.action == 'lesson' and args.lesson_action in ('list', 'show'):
            state = load(Path(args.root).expanduser().resolve())
            if args.lesson_action == 'show':
                result = find(state, args.id, 'L')
            else:
                result = {'lessons': [{'id': r['id'], 'status': r['status'], 'target': r['target'],
                                       'text': r['text'], 'document': r['document'],
                                       'source_feedback': r['source_feedback']}
                                      for r in state['lessons']]}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        result = execute(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
