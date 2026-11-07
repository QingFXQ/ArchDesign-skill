"""Versioned project records, artifact lifecycle and delivery validation gates."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from check_layout import check

SCHEMA_VERSION = 2
STAGES = ('research', 'concept', 'scheme', 'production', 'visualization', 'presentation', 'delivery')
ARTIFACT_STATUS = ('active', 'superseded', 'archived')
PROJECT_TARGET = 'project'

# A requirement names exactly one check. The check decides which lane produces
# admissible evidence; nothing outside that lane may satisfy it.
VISUAL_CHECKS = {'visual_whole_board': 'whole_board',
                 'visual_drawing_local': 'drawing_local',
                 'visual_print': 'print',
                 'visual_cross_drawing': 'cross_drawing'}
HOST_CHECKS = {'cad_reopen': ('dwg',), 'cad_layers': ('dwg',), 'cad_dimensions': ('dwg',),
               'cad_editability': ('dwg',),
               'revit_reopen': ('rvt',), 'revit_objects': ('rvt',), 'revit_model_state': ('rvt',),
               'blender_reopen': ('blend',), 'blender_objects': ('blend',), 'blender_scene': ('blend',),
               'psd_layers': ('psd',), 'psd_text': ('psd',), 'psd_placed': ('psd',), 'psd_reopen': ('psd',)}
PROJECT_CHECKS = ('automatic_check',)
# Universal checks apply to every artifact; a kind only adds its own software checks.
KIND_CHECKS = {'*': ['visual_whole_board'],
               'pdf': ['visual_print'],
               'dwg': ['cad_reopen', 'cad_layers', 'cad_dimensions', 'cad_editability'],
               'rvt': ['revit_reopen', 'revit_objects', 'revit_model_state'],
               'blend': ['blender_reopen', 'blender_objects', 'blender_scene'],
               'psd': ['psd_layers', 'psd_text', 'psd_placed', 'psd_reopen']}
NEGATIVE_CONCLUSIONS = ('needs_rework',)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_file(root, value):
    path = (root / Path(value).expanduser()).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Project evidence must stay inside the project directory')
    if not path.is_file():
        raise ValueError(f'Evidence missing: {path}')
    return path


def project_path(root, value):
    path = (root / Path(value).expanduser()).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Project evidence must stay inside the project directory')
    return path


def rel(root, path):
    return path.relative_to(root).as_posix()


def save(path, state):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def status_of(row):
    return row.get('status', 'active')


def check_lane(name):
    if name in PROJECT_CHECKS:
        return 'automatic'
    if name in VISUAL_CHECKS:
        return 'visual'
    if name in HOST_CHECKS:
        return 'host'
    known = ', '.join(PROJECT_CHECKS + tuple(VISUAL_CHECKS) + tuple(HOST_CHECKS))
    raise ValueError(f'Unknown validation check {name!r}; known checks: {known}')


def kind_checks(kind):
    checks = list(KIND_CHECKS['*'])
    for name in KIND_CHECKS.get(kind, ()):
        if name not in checks:
            checks.append(name)
    return checks


def override(state, target, name):
    for row in state.get('requirements', []):
        if row['target'] == target and row['check'] == name:
            return row
    return None


def requirements_for(state, artifact):
    """Defaults for the artifact kind, overridden or extended by explicit declarations."""
    checks = kind_checks(artifact['kind'])
    rows = []
    for name in checks:
        declared = override(state, artifact['path'], name) or override(state, PROJECT_TARGET, name)
        rows.append((name, declared['status'] if declared else 'required',
                     (declared or {}).get('reason', '')))
    names = [row[0] for row in rows]
    for declared in state.get('requirements', []):
        if declared['check'] in names or declared['check'] == 'automatic_check':
            continue
        if declared['target'] in (artifact['path'], PROJECT_TARGET):
            rows.append((declared['check'], declared['status'], declared.get('reason', '')))
            names.append(declared['check'])
    return rows


def migrate(state):
    """Schema 1 kept a flat review dictionary with no artifact binding."""
    version = state.get('schema_version')
    if version == SCHEMA_VERSION:
        state.setdefault('validations', [])
        state.setdefault('requirements', [])
        state.setdefault('sequence', len(state.get('artifacts', [])))
        for row in state['artifacts']:
            row.setdefault('status', 'active')
            row.setdefault('supersedes', [])
        return state
    if version != 1:
        raise ValueError('Unsupported project schema')
    state['sequence'] = len(state['artifacts'])
    art = state['artifacts']
    for number, row in enumerate(art, 1):
        row['id'] = row.get('id', f'A-{number:04d}')
        row.setdefault('status', 'active')
        row.setdefault('supersedes', [])
        row.setdefault('superseded_by', None)
        row.setdefault('superseded_reason', None)
    validations = []
    reviews = state.get('reviews') or {}
    automatic = reviews.get('automatic')
    if automatic:
        validations.append({'id': 'V-0001', 'lane': 'automatic', 'check': 'automatic_check',
                            'revision': automatic.get('revision'), 'passed': bool(automatic.get('passed')),
                            'evidence': {'path': automatic.get('path'), 'sha256': automatic.get('sha256')},
                            'inputs': automatic.get('inputs', {}),
                            'migrated_from': 'reviews.automatic'})
    visual = reviews.get('visual')
    if visual:
        bound = [{'path': row['path'], 'sha256': row['sha256'], 'artifact_id': row['id']}
                 for row in art if row.get('revision') == visual.get('revision')]
        validations.append({'id': f'V-{len(validations) + 1:04d}', 'lane': 'visual', 'check': 'visual_review',
                            'revision': visual.get('revision'), 'scopes': ['whole_board'],
                            'conclusion': 'accepted', 'note': visual.get('note', ''), 'artifacts': bound,
                            'evidence': {'path': visual.get('path'), 'sha256': visual.get('sha256')},
                            'migrated_from': 'reviews.visual', 'legacy': True})
    host = reviews.get('host')
    if host:
        # A schema 1 host note never recorded which check ran or whether it passed.
        validations.append({'id': f'V-{len(validations) + 1:04d}', 'lane': 'host', 'check': 'legacy_host_review',
                            'revision': host.get('revision'), 'result': 'unrecorded', 'artifacts': [],
                            'evidence': {'path': host.get('path'), 'sha256': host.get('sha256')},
                            'note': host.get('note', ''), 'migrated_from': 'reviews.host', 'legacy': True})
    state['validations'] = validations
    state['requirements'] = []
    state.pop('reviews', None)
    state['schema_version'] = SCHEMA_VERSION
    state.setdefault('decisions', [])
    state.setdefault('history', [])
    return state


def latest(state, lane, name, artifact_path=None):
    rows = [row for row in state['validations']
            if row.get('lane') == lane and row.get('revision') == state['revision']]
    if lane == 'visual':
        scope = VISUAL_CHECKS[name]
        # A migrated schema 1 record never declared a scope. It keeps the old coverage of
        # the project it was written for and stays marked as legacy in the delivery report.
        rows = [row for row in rows
                if (row.get('legacy')
                    or scope in row.get('scopes', []))
                and any(x['path'] == artifact_path for x in row.get('artifacts', []))]
    elif lane == 'host':
        rows = [row for row in rows if row.get('check') == name
                and any(x['path'] == artifact_path for x in row.get('artifacts', []))]
    else:
        rows = [row for row in rows if row.get('check') == name]
    return rows[-1] if rows else None


def validation_problems(root, state, record):
    """Why a recorded validation no longer supports the current revision, if it does not."""
    problems = []
    if record.get('revision') != state['revision']:
        problems.append(f'recorded for revision {record.get("revision")}')
    evidence = record.get('evidence') or {}
    try:
        if digest(local_file(root, evidence.get('path', ''))) != evidence.get('sha256'):
            problems.append('review evidence changed')
    except ValueError as exc:
        problems.append(str(exc))
    for path, sha in (record.get('inputs') or {}).items():
        try:
            if digest(local_file(root, path)) != sha:
                problems.append('Checked input changed: ' + path)
        except ValueError as exc:
            problems.append(str(exc))
    by_id = {row.get('id'): row for row in state['artifacts']}
    for bound in record.get('artifacts') or []:
        row = by_id.get(bound.get('artifact_id'))
        if row is None:
            row = next((r for r in state['artifacts']
                        if r['path'] == bound['path'] and status_of(r) == 'active'), None)
        if row is None:
            problems.append('artifact no longer registered: ' + bound['path'])
        elif status_of(row) != 'active':
            problems.append(f'artifact {status_of(row)}: {bound["path"]} ({row.get("id")})')
        elif bound.get('artifact_id') and row.get('id') != bound['artifact_id']:
            problems.append('artifact re-registered: ' + bound['path'])
        elif row['sha256'] != bound['sha256']:
            problems.append('artifact content changed: ' + bound['path'])
        else:
            try:
                if digest(local_file(root, bound['path'])) != bound['sha256']:
                    problems.append('reviewed file changed on disk: ' + bound['path'])
            except ValueError as exc:
                problems.append(str(exc))
    return problems


def gate(root, state):
    errors, warnings, waived, validated = [], [], [], []
    active = [row for row in state['artifacts'] if status_of(row) == 'active']
    if not active:
        errors.append('No active delivery artifacts registered')
    for row in active:
        try:
            path = local_file(root, row['path'])
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if digest(path) != row['sha256']:
            errors.append('Artifact changed: ' + row['path'])
        if row['revision'] != state['revision']:
            errors.append('Stale artifact revision: ' + row['path'])

    declared = override(state, PROJECT_TARGET, 'automatic_check')
    if declared and declared['status'] == 'not_applicable':
        if not declared.get('reason', '').strip():
            errors.append('Waiver without reason: automatic_check')
        else:
            waived.append({'target': PROJECT_TARGET, 'check': 'automatic_check',
                           'reason': declared['reason']})
    else:
        record = latest(state, 'automatic', 'automatic_check')
        if record is None:
            errors.append('Missing required validation: automatic_check')
        else:
            problems = validation_problems(root, state, record)
            if problems:
                errors.append('Automatic check evidence invalid: ' + '; '.join(problems))
            elif not record.get('passed'):
                errors.append('Automatic checks failed')
            else:
                validated.append({'target': PROJECT_TARGET, 'check': 'automatic_check',
                                  'evidence': record['id']})
            inputs = record.get('inputs') or {}
            for row in active:
                if row['kind'] == 'pdf' and row['path'] not in inputs:
                    warnings.append('Automatic check does not cover active artifact: ' + row['path'])

    for row in active:
        for name, status, reason in requirements_for(state, row):
            if status == 'not_applicable':
                if not reason.strip():
                    errors.append(f'Waiver without reason: {name} for {row["path"]}')
                else:
                    waived.append({'target': row['path'], 'check': name, 'reason': reason})
                continue
            lane = check_lane(name)
            if lane == 'automatic':
                continue
            record = latest(state, lane, name, row['path'])
            if record is None:
                errors.append(f'Missing required validation: {name} for {row["path"]}')
                continue
            problems = validation_problems(root, state, record)
            if problems:
                errors.append(f'Evidence no longer valid: {name} for {row["path"]} '
                              f'({"; ".join(problems)})')
            elif lane == 'visual' and record.get('conclusion') in NEGATIVE_CONCLUSIONS:
                errors.append(f'Visual review requires rework: {name} for {row["path"]}')
            elif lane == 'host' and record.get('result') != 'passed':
                errors.append(f'Host validation not passed: {name} for {row["path"]}')
            else:
                entry = {'target': row['path'], 'check': name, 'evidence': record['id']}
                if record.get('legacy'):
                    entry['legacy'] = True
                validated.append(entry)
    return {'errors': errors, 'warnings': warnings, 'waived': waived, 'validated': validated,
            'active_artifacts': [row['path'] for row in active],
            'superseded_artifacts': [row['path'] for row in state['artifacts']
                                     if status_of(row) == 'superseded'],
            'archived_artifacts': [row['path'] for row in state['artifacts']
                                   if status_of(row) == 'archived']}


def bind(root, state, values, allow_all_active):
    rows = []
    for value in values or []:
        path = local_file(root, value)
        name = rel(root, path)
        row = next((r for r in state['artifacts']
                    if r['path'] == name and status_of(r) == 'active'), None)
        if row is None:
            raise ValueError(f'Review target is not an active artifact: {name}')
        rows.append({'path': name, 'sha256': row['sha256'], 'artifact_id': row.get('id')})
    if rows:
        return rows
    if not allow_all_active:
        raise ValueError('A visual review must name at least one active artifact')
    rows = [{'path': r['path'], 'sha256': r['sha256'], 'artifact_id': r.get('id')}
            for r in state['artifacts']
            if status_of(r) == 'active' and r['revision'] == state['revision']]
    if not rows:
        raise ValueError('No active artifact at this revision to bind the review to')
    return rows


def register_artifact(root, state, args):
    path = local_file(root, args.path)
    name = rel(root, path)
    status = args.status
    sha = digest(path)
    number = state.get('sequence', len(state['artifacts'])) + 1
    row = {'id': f'A-{number:04d}', 'path': name, 'sha256': sha, 'revision': state['revision'],
           'kind': args.kind, 'status': status, 'supersedes': [], 'superseded_by': None,
           'superseded_reason': None}
    state['sequence'] = number
    if status == 'active':
        declared = {rel(root, local_file(root, v)) for v in (args.supersedes or [])}
        missing = declared - {r['path'] for r in state['artifacts']}
        if missing:
            raise ValueError('Declared superseded artifact not registered: ' + ', '.join(sorted(missing)))
        targets = [r for r in state['artifacts'] if status_of(r) == 'active']
        superseded = []
        for old in targets:
            reason = None
            if old['path'] in declared:
                reason = 'superseded_by_declaration'
            elif old['path'] == name:
                reason = 'replaced_by_newer_registration'
            elif old['revision'] != state['revision']:
                reason = 'revision_advanced'
            if reason:
                old['status'] = 'superseded'
                old['superseded_by'] = row['id']
                old['superseded_reason'] = reason
                row['supersedes'].append(old['id'])
                superseded.append({'id': old['id'], 'path': old['path'],
                                   'sha256': old['sha256'], 'revision': old['revision'],
                                   'reason': reason})
        state['artifacts'].append(row)
        return row, superseded
    state['artifacts'].append(row)
    return row, []


def execute(args):
    root = Path(args.root).expanduser().resolve()
    path = root / 'project.json'
    if args.action == 'init':
        if path.exists():
            raise ValueError('Project already exists; resume its current revision')
        root.mkdir(parents=True, exist_ok=True)
        state = {'schema_version': SCHEMA_VERSION, 'revision': args.revision, 'stage': 'research',
                 'brief': args.brief, 'artifacts': [], 'decisions': [], 'validations': [],
                 'requirements': [], 'history': [], 'sequence': 0}
        save(path, state)
        return state
    state = migrate(json.loads(path.read_text(encoding='utf-8-sig')))
    if args.action == 'checkpoint':
        state['history'].append({'revision': state['revision'], 'stage': state['stage'],
                                 'reason': args.reason,
                                 'artifacts': [{'path': r['path'], 'status': status_of(r)}
                                               for r in state['artifacts']],
                                 'validations': len(state['validations'])})
        state.update(revision=args.revision, stage=args.stage)
    elif args.action == 'artifact':
        row, superseded = register_artifact(root, state, args)
        save(path, state)
        return {'artifact': row, 'superseded': superseded}
    elif args.action == 'archive':
        name = rel(root, project_path(root, args.path))
        row = next((r for r in state['artifacts']
                    if r['path'] == name and status_of(r) == 'active'), None)
        if row is None:
            raise ValueError('No active artifact with that path: ' + name)
        if not args.reason.strip():
            raise ValueError('Archiving an artifact needs a recorded reason')
        row['status'] = 'archived'
        row['archive_reason'] = args.reason
        save(path, state)
        return row
    elif args.action == 'decision':
        state['decisions'].append({'revision': state['revision'], 'scope': args.scope,
                                   'user_text': args.text})
    elif args.action == 'require':
        check_lane(args.check)
        target = PROJECT_TARGET
        if args.check in PROJECT_CHECKS and args.artifact:
            raise ValueError(f'{args.check} is a project-level requirement; omit --artifact')
        if args.check in HOST_CHECKS and args.artifact is None:
            raise ValueError(f'{args.check} is a per-artifact host check; pass --artifact')
        if args.artifact:
            target = rel(root, project_path(root, args.artifact))
            row = next((r for r in state['artifacts'] if r['path'] == target), None)
            if row is not None and args.check in HOST_CHECKS and row['kind'] not in HOST_CHECKS[args.check]:
                raise ValueError(f'{args.check} does not apply to kind {row["kind"]}')
        if args.status == 'not_applicable' and not args.reason.strip():
            raise ValueError('A not_applicable requirement needs a recorded reason')
        state['requirements'] = [r for r in state['requirements']
                                 if not (r['target'] == target and r['check'] == args.check)]
        state['requirements'].append({'target': target, 'check': args.check, 'status': args.status,
                                      'reason': args.reason})
    elif args.action == 'review':
        evidence = local_file(root, args.evidence)
        number = len(state['validations']) + 1
        if args.kind == 'visual':
            scopes = list(dict.fromkeys(args.scope or ['whole_board']))
            for name in scopes:
                if name not in VISUAL_CHECKS.values():
                    raise ValueError(f'Unknown review scope {name!r}')
            record = {'id': f'V-{number:04d}', 'lane': 'visual', 'check': 'visual_review',
                      'revision': state['revision'], 'scopes': scopes,
                      'conclusion': args.conclusion, 'note': args.note,
                      'artifacts': bind(root, state, args.artifact, True),
                      'evidence': {'path': rel(root, evidence), 'sha256': digest(evidence)}}
        else:
            if args.check not in HOST_CHECKS:
                raise ValueError('Host validation needs one of: ' + ', '.join(HOST_CHECKS))
            if not args.artifact or len(args.artifact) != 1:
                raise ValueError('One host validation covers exactly one artifact')
            target = bind(root, state, args.artifact, False)[0]
            row = next(r for r in state['artifacts']
                       if r.get('id') == target.get('artifact_id'))
            if row['kind'] not in HOST_CHECKS[args.check]:
                raise ValueError(f'{args.check} does not apply to kind {row["kind"]}')
            if evidence.name == 'automatic-checks.json':
                raise ValueError('Host validation must cite host evidence, '
                                 'not automated check output')
            sha = digest(evidence)
            if any(sha == (v.get('evidence') or {}).get('sha256')
                   for v in state['validations'] if v.get('lane') == 'automatic'):
                raise ValueError('Host validation must cite host evidence, '
                                 'not a copy of automated check output')
            record = {'id': f'V-{number:04d}', 'lane': 'host', 'check': args.check,
                      'revision': state['revision'], 'result': args.result, 'note': args.note,
                      'artifacts': [target],
                      'evidence': {'path': rel(root, evidence), 'sha256': sha}}
        state['validations'].append(record)
        save(path, state)
        return record
    elif args.action == 'check':
        layout = local_file(root, args.layout)
        pdf = local_file(root, args.pdf)
        data = json.loads(layout.read_text(encoding='utf-8-sig'))
        result = check(data, layout.parent, pdf)
        if not data.get('expected_revision'):
            result['warnings'].append('layout declares no expected_revision; '
                                      'the source revision was not compared')
        report = {'revision': state['revision'], 'errors': result['errors'], 'layout': result,
                  'automatic_checks': 'failed' if result['errors'] else 'passed'}
        dest = root / 'automatic-checks.json'
        save(dest, report)
        record = {'id': f'V-{len(state["validations"]) + 1:04d}', 'lane': 'automatic',
                  'check': 'automatic_check', 'revision': state['revision'],
                  'passed': not result['errors'],
                  'evidence': {'path': dest.name, 'sha256': digest(dest)},
                  'inputs': {rel(root, p): digest(p) for p in (layout, pdf)}}
        state['validations'].append(record)
        save(path, state)
        return report
    elif args.action == 'deliver':
        result = gate(root, state)
        errors = list(result['errors'])
        if not any(d['revision'] == state['revision'] and d['scope'] == 'delivery'
                   for d in state['decisions']):
            errors.append('Missing explicit user delivery decision for this revision')
        if errors:
            return {'delivery': 'blocked', 'revision': state['revision'], 'errors': errors,
                    'warnings': result['warnings'], 'waived': result['waived'],
                    'validated': result['validated'],
                    'active_artifacts': result['active_artifacts'],
                    'superseded_artifacts': result['superseded_artifacts'],
                    'archived_artifacts': result['archived_artifacts']}
        state['stage'] = 'delivery'
        save(path, state)
        return {'delivery': 'accepted', 'revision': state['revision'],
                'validated': result['validated'], 'waived': result['waived'],
                'warnings': result['warnings'],
                'active_artifacts': result['active_artifacts'],
                'superseded_artifacts': result['superseded_artifacts'],
                'archived_artifacts': result['archived_artifacts'],
                'host_integrations': 'Host checks are recorded only through recorded host evidence; '
                                     'offline checks never verify design software'}
    elif args.action == 'status':
        view = dict(state)
        view['gate_summary'] = gate(root, state)
        return view
    save(path, state)
    return state


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', required=True)
    sub = p.add_subparsers(dest='action', required=True)
    q = sub.add_parser('init')
    q.add_argument('--brief', required=True)
    q.add_argument('--revision', default='R1')
    q = sub.add_parser('checkpoint')
    q.add_argument('--revision', required=True)
    q.add_argument('--stage', choices=STAGES, required=True)
    q.add_argument('--reason', required=True)
    q = sub.add_parser('artifact')
    q.add_argument('--path', required=True)
    q.add_argument('--kind', required=True)
    q.add_argument('--supersedes', action='append', default=[])
    q.add_argument('--status', choices=ARTIFACT_STATUS, default='active')
    q = sub.add_parser('archive')
    q.add_argument('--path', required=True)
    q.add_argument('--reason', default='')
    q = sub.add_parser('decision')
    q.add_argument('--scope', choices=['concept', 'scheme', 'camera', 'delivery'], required=True)
    q.add_argument('--text', required=True)
    q = sub.add_parser('require')
    q.add_argument('--check', required=True)
    q.add_argument('--artifact')
    q.add_argument('--status', choices=['required', 'not_applicable'], default='required')
    q.add_argument('--reason', default='')
    q = sub.add_parser('review')
    q.add_argument('--kind', choices=['visual', 'host'], required=True)
    q.add_argument('--evidence', required=True)
    q.add_argument('--note', required=True)
    q.add_argument('--artifact', action='append', default=[])
    q.add_argument('--scope', action='append', default=[])
    q.add_argument('--conclusion', choices=['accepted', 'accepted_with_notes', 'needs_rework'],
                   default='accepted')
    q.add_argument('--check')
    q.add_argument('--result', choices=['passed', 'failed'], default='passed')
    q = sub.add_parser('check')
    q.add_argument('--layout', required=True)
    q.add_argument('--pdf', required=True)
    sub.add_parser('deliver')
    sub.add_parser('status')
    try:
        result = execute(p.parse_args())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result.get('errors') else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
