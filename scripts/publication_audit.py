"""Scan the checkout for content that cannot be published as-is; never edits files."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills/architecture-design-workflow'
HISTORY = SKILL / 'assets/history'
CORPUS = SKILL / 'assets/knowledge/architecture-case-rag'
ALLOWLIST = ROOT / 'audit/publication-audit.allow.json'
SKIP_PARTS = ('.git', '__pycache__', '.venv', 'node_modules', '.codegraph')
# This report quotes the very paths it finds, and this scanner embeds the path patterns,
# so scanning either back would inflate every run.
SKIP_FILES = ('audit/publication-audit.json', 'scripts/publication_audit.py')
PLACEHOLDER = re.compile(r'\\path\\to|C:\\path\\|\.\.\.|<[A-Za-z\u4e00-\u9fff]+>')
TEXT_SUFFIXES = ('.md', '.py', '.json', '.yaml', '.yml', '.txt', '.csv', '.js', '.mjs', '.ts',
                 '.html', '.css', '.svg', '.toml', '.example')
LARGE_BYTES = 5 * 1024 * 1024

SECRETS = (('private key', re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY')),
           ('github token', re.compile(r'\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}')),
           ('github fine-grained token', re.compile(r'\bgithub_pat_[A-Za-z0-9_]{20,}')),
           ('api key', re.compile(r'\b(?:sk|rk)-[A-Za-z0-9]{20,}')),
           ('aws key', re.compile(r'\bAKIA[0-9A-Z]{16}\b')),
           ('slack token', re.compile(r'\bxox[baprs]-[A-Za-z0-9-]{10,}')),
           ('bearer header', re.compile(r'Authorization\s*:\s*Bearer\s+[A-Za-z0-9._-]{20,}')))
PATHS = (('windows absolute path', re.compile(r'(?<![A-Za-z0-9])[A-Za-z]:[\\/]{1,2}[^\s"\'`,;)]{3,}')),
         ('unix home path', re.compile(r'(?<![\w/])/(?:home|Users)/[A-Za-z0-9._-]+/[^\s"\'`,;)]*')),
         ('unc path', re.compile(r'\\\\[A-Za-z0-9._-]+\\[^\s"\'`,;)]+')))
EMAIL = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
# Test fixtures must contain credentials that match the patterns above. Writing the marker
# FAKECREDENTIAL next to them keeps the finding visible but no longer treats it as a leak.
FAKE_MARKER = 'fakecredential'
COMMUNITY_FILES = ('CONTRIBUTING.md', 'CODE_OF_CONDUCT.md', 'SECURITY.md', 'SUPPORT.md',
                   '.github/PULL_REQUEST_TEMPLATE.md', '.github/ISSUE_TEMPLATE/config.yml')
ISSUE_FORMS = ('bug_report.yml', 'feature_proposal.yml', 'knowledge_contribution.yml',
               'tool_adapter.yml')


def files():
    for path in ROOT.rglob('*'):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in SKIP_PARTS for part in relative.parts):
            continue
        if relative.as_posix() in SKIP_FILES:
            continue
        yield path


def category(path):
    if path.is_relative_to(HISTORY):
        return 'history'
    if path.is_relative_to(CORPUS / 'cases') or path.is_relative_to(CORPUS / 'index'):
        return 'case-corpus'
    if path.is_relative_to(ROOT / 'audit'):
        return 'audit'
    return 'active'


def scan_text(path):
    findings = []
    try:
        text = path.read_text(encoding='utf-8-sig')
    except (UnicodeError, OSError):
        return findings
    relative = path.relative_to(ROOT).as_posix()
    for number, line in enumerate(text.splitlines(), 1):
        claimed = []
        for label, pattern in SECRETS:
            for match in pattern.finditer(line):
                claimed.append(match.span())
                placeholder = FAKE_MARKER in line.lower()
                findings.append({'kind': 'secret',
                                 'severity': 'review_required' if placeholder else 'blocker',
                                 'rule': label + (' (test placeholder)' if placeholder else ''),
                                 'file': relative, 'line': number,
                                 'text': '<withheld: possible credential>'})
        for label, pattern in PATHS:
            for match in pattern.finditer(line):
                span = match.span()
                if any(start <= span[0] and span[1] <= end for start, end in claimed):
                    continue
                if PLACEHOLDER.search(match.group(0)):
                    continue
                claimed.append(span)
                findings.append({'kind': 'local-path', 'severity': 'review_required',
                                 'rule': label, 'file': relative, 'line': number,
                                 'text': match.group(0).replace('\\\\', '\\')[:120]})
        for match in EMAIL.finditer(line):
            if not match.group(0).lower().endswith(('@users.noreply.github.com', '@example.com')):
                findings.append({'kind': 'email', 'severity': 'review_required',
                                 'rule': 'email address', 'file': relative, 'line': number,
                                 'text': match.group(0)[:120]})
    return findings


def community_state():
    missing = [name for name in COMMUNITY_FILES if not (ROOT / name).is_file()]
    forms = [name for name in ISSUE_FORMS
             if (ROOT / '.github/ISSUE_TEMPLATE' / name).is_file()]
    license_files = [name for name in ('LICENSE', 'LICENSE.md', 'COPYING', 'COPYING.md')
                     if (ROOT / name).is_file()]
    readme = (ROOT / 'README.md').read_text(encoding='utf-8', errors='ignore') \
        if (ROOT / 'README.md').is_file() else ''
    return {'missing_community_files': missing, 'issue_forms': forms,
            'license_file': license_files[0] if license_files else None,
            'readme_states_license': bool(re.search(r'licen[cs]e|许可证|授权协议', readme, re.I))}


def third_party():
    index = CORPUS / 'index/cases.json'
    if not index.is_file():
        return {'case_records': 0, 'sources': {}, 'records_with_source_url': 0}
    data = json.loads(index.read_text(encoding='utf-8'))
    rows = data.get('cases', []) if isinstance(data, dict) else data
    hosts, with_url = {}, 0
    for row in rows:
        for source in row.get('sources') or []:
            url = source.get('url', '') if isinstance(source, dict) else str(source)
            host = re.sub(r'^https?://', '', url).split('/')[0]
            if host:
                hosts[host] = hosts.get(host, 0) + 1
                with_url += 1
    return {'case_records': len(rows), 'sources': dict(sorted(hosts.items(), key=lambda kv: -kv[1])),
            'records_with_source_url': with_url, 'license_field_present': any(
                'license' in row for row in rows)}


def large_files():
    rows = []
    for path in files():
        size = path.stat().st_size
        if size >= LARGE_BYTES:
            rows.append({'file': path.relative_to(ROOT).as_posix(), 'bytes': size,
                         'sha256': hashlib.sha256(path.read_bytes()).hexdigest()[:16],
                         'category': category(path)})
    return sorted(rows, key=lambda row: -row['bytes'])


def lfs_patterns():
    attributes = ROOT / '.gitattributes'
    if not attributes.is_file():
        return []
    return [line.strip() for line in attributes.read_text(encoding='utf-8').splitlines()
            if 'filter=lfs' in line]


def allowlisted(finding, rules):
    relative = finding['file']
    for rule in rules:
        prefix = rule.get('path', '')
        if prefix and not (relative == prefix or relative.startswith(prefix.rstrip('/') + '/')):
            continue
        if rule.get('kind') and rule['kind'] != finding['kind']:
            continue
        if rule.get('text_contains') and rule['text_contains'] not in finding['text']:
            continue
        return rule.get('reason', '')
    return None


def audit():
    findings = []
    for path in files():
        if path.suffix.lower() in TEXT_SUFFIXES:
            findings.extend(scan_text(path))
    rules = []
    if ALLOWLIST.is_file():
        rules = json.loads(ALLOWLIST.read_text(encoding='utf-8')).get('allow', [])
    for finding in findings:
        finding['category'] = category(Path(ROOT / finding['file']))
        reason = allowlisted(finding, rules)
        finding['allowlisted'] = bool(reason)
        if reason:
            finding['allow_reason'] = reason
    open_findings = [row for row in findings if not row['allowlisted']]
    by_severity = {'blocker': 0, 'review_required': 0, 'info': 0}
    for row in open_findings:
        by_severity[row['severity']] = by_severity.get(row['severity'], 0) + 1
    community = community_state()
    # Active files are the publication blockers people must read line by line; retained
    # history and generated audit reports are summarised per file so the report stays usable.
    active = [row for row in open_findings if row['category'] == 'active']
    retained = [row for row in open_findings if row['category'] != 'active']
    per_file = {}
    for row in retained:
        entry = per_file.setdefault(row['file'], {'file': row['file'], 'category': row['category'],
                                                  'count': 0, 'kinds': set(), 'example': row['text']})
        entry['count'] += 1
        entry['kinds'].add(row['kind'])
    retained_files = sorted(per_file.values(), key=lambda row: (-row['count'], row['file']))
    for entry in retained_files:
        entry['kinds'] = sorted(entry['kinds'])
    report = {
        'repository': 'QingFXQ/ArchDesigh.skill',
        'checkout': ROOT.name,
        'files_scanned': sum(1 for _ in files()),
        'verdict': 'blocked' if by_severity['blocker'] else
                   'review' if by_severity['review_required'] else 'ready',
        'severity_counts': by_severity,
        'community': community,
        'license': {'file': community['license_file'],
                    'readme_mentions': community['readme_states_license'],
                    'status': 'declared' if community['license_file'] else 'missing'},
        'third_party': third_party(),
        'large_files': large_files(),
        'lfs_patterns': lfs_patterns(),
        'active_findings': active,
        'retained_findings': {'occurrences': len(retained), 'files': retained_files},
        'allowlisted_findings': [row for row in findings if row['allowlisted']],
        'by_kind': {kind: sum(1 for row in open_findings if row['kind'] == kind)
                    for kind in sorted({row['kind'] for row in open_findings})},
        'by_category': {name: sum(1 for row in open_findings if row['category'] == name)
                        for name in ('active', 'history', 'case-corpus', 'audit')},
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    # Windows consoles default to a legacy code page; findings and summaries contain CJK.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    parser.add_argument('--report', default='audit/publication-audit.json')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--limit', type=int, default=8)
    args = parser.parse_args()
    report = audit()
    if args.report:
        target = ROOT / args.report
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                          encoding='utf-8')
    summary = {key: report[key] for key in ('verdict', 'severity_counts', 'by_kind',
                                            'by_category', 'license')}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for row in report['active_findings'][:args.limit]:
        print(f"  [active/{row['kind']}] {row['file']}:{row['line']} {row['text']}")
    for row in report['retained_findings']['files'][:args.limit]:
        print(f"  [retained/{row['category']}] {row['file']} x{row['count']} {row['example'][:80]}")
    print(f"Total path/secret findings: {sum(report['severity_counts'].values())} "
          f"(active {len(report['active_findings'])}, "
          f"retained {report['retained_findings']['occurrences']} in "
          f"{len(report['retained_findings']['files'])} files)")
    print(f"Community files missing: {len(report['community']['missing_community_files'])}; "
          f"issue forms: {len(report['community']['issue_forms'])}/4; "
          f"large files: {len(report['large_files'])}; "
          f"case records: {report['third_party']['case_records']}")
    return 1 if args.check and report['verdict'] == 'blocked' else 0


if __name__ == '__main__':
    raise SystemExit(main())
