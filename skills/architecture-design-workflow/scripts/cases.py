"""Read a local board catalog and build uncropped visual comparisons, without editing it."""
import argparse
import json
import os
from pathlib import Path
import re
import sys


def catalog_path(explicit=None):
    if explicit:
        return Path(explicit).expanduser().resolve()
    if os.environ.get('ARCH_LAYOUT_CATALOG'):
        return Path(os.environ['ARCH_LAYOUT_CATALOG']).expanduser()
    home = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex').expanduser()
    cfg = home / 'architecture-resources.json'
    if cfg.is_file():
        value = json.loads(cfg.read_text(encoding='utf-8-sig')).get('layout_catalog')
        if value:
            p = Path(value).expanduser()
            return (p if p.is_absolute() else cfg.parent/p).resolve()
    raise ValueError('No catalog configured; use --catalog or local architecture-resources.json')


def load_cases(path):
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if isinstance(data, dict):
        data = data.get('cases', data.get('entries'))
    if not isinstance(data, list) or not all(isinstance(c, dict) for c in data):
        raise ValueError('Catalog must be a list, or an object with cases/entries list')
    result = []
    for c in data:
        cid = c.get('case_id', c.get('id'))
        if not isinstance(cid, str) or not cid:
            raise ValueError('Every catalog record needs case_id/id')
        result.append(c)
    ids = [identity(c) for c in result]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate case IDs; resolve record identities before selecting')
    return result


def identity(c):
    return c.get('case_id', c.get('id'))


def image_paths(c, base):
    values = c.get('display_images') or [i.get('source_path') for i in c.get('images', [])]
    paths = []
    for value in values:
        if not value:
            continue
        p = Path(value).expanduser()
        paths.append(p if p.is_absolute() else base / p)
    return paths


def select(cases, query='', ids=None, orientation=None, complete=False, limit=6):
    if ids:
        mapping = {identity(c): c for c in cases}
        missing = [cid for cid in ids if cid not in mapping]
        if missing:
            raise ValueError('Unknown case IDs: ' + ', '.join(missing))
        return [mapping[cid] for cid in dict.fromkeys(ids)]
    words = re.findall(r'\S+', query.casefold())
    scored = []
    for c in cases:
        if c.get('status') in ('排除', 'excluded'):
            continue
        if orientation and orientation not in str(c.get('orientation', '')):
            continue
        if complete and c.get('complete_set') is not True:
            continue
        fields = [c.get(k, '') for k in ('work_name', 'note_title', 'title', 'category',
                  'style', 'orientation', 'components', 'organization', 'tags')]
        haystack = json.dumps(fields, ensure_ascii=False).casefold()
        score = sum(word in haystack for word in words)
        if not words or score:
            scored.append((score, identity(c), c))
    # Score means keyword overlap only, not beauty, verification or user preference.
    return [c for _, _, c in sorted(scored, key=lambda row: (-row[0], row[1]))[:limit]]


def contact(cases, base, output, font_path=None):
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    rows = [(identity(c), n+1, p) for c in cases for n, p in enumerate(image_paths(c, base))]
    if not rows:
        raise ValueError('Selected records have no local display images')
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    results = []
    font = ImageFont.truetype(font_path, 18) if font_path else ImageFont.load_default()
    for offset in range(0, len(rows), 12):
        batch = rows[offset:offset+12]
        canvas = Image.new('RGB', (1200, ((len(batch)+3)//4)*420), '#e9e9e5')
        draw = ImageDraw.Draw(canvas)
        for i, (cid, order, path) in enumerate(batch):
            x, y = (i % 4)*300, (i//4)*420
            try:
                with Image.open(path) as src:
                    tile = ImageOps.exif_transpose(src).convert('RGB')
                    tile.thumbnail((286, 380))
                    canvas.paste(tile, (x+(300-tile.width)//2, y+4))
            except (OSError, ValueError) as exc:
                raise ValueError(f'Cannot open {path}: {exc}') from exc
            draw.text((x+8, y+391), f'{cid} / {order}', font=font, fill='#222222')
        dest = output if len(rows) <= 12 else output.with_name(f'{output.stem}_{offset//12+1:02d}{output.suffix}')
        canvas.save(dest)
        results.append(str(dest))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog')
    parser.add_argument('--query', default='')
    parser.add_argument('--ids', nargs='+')
    parser.add_argument('--orientation', choices=['竖向', '横向', 'portrait', 'landscape'])
    parser.add_argument('--complete-only', action='store_true')
    parser.add_argument('--limit', type=int, default=6)
    parser.add_argument('--contact', help='Local output image; paginate at 12 full images, never crop')
    parser.add_argument('--font', help='Optional installed font path for contact sheet labels')
    args = parser.parse_args()
    if args.limit < 1:
        parser.error('--limit must be positive')
    try:
        path = catalog_path(args.catalog)
        cases = load_cases(path)
        chosen = select(cases, args.query, args.ids, args.orientation, args.complete_only, args.limit)
        report = {'catalog': str(path), 'record_count': len(cases),
                  'selection_basis': 'keyword match, not aesthetic approval', 'cases': []}
        for c in chosen:
            images = image_paths(c, path.parent)
            report['cases'].append({
                'id': identity(c), 'title': c.get('work_name') or c.get('note_title') or c.get('title', ''),
                'status': c.get('status', 'unknown'), 'category': c.get('category', ''),
                'format_claim': c.get('format', 'unknown'), 'format_evidence': c.get('format_evidence', ''),
                'complete_set_claim': c.get('complete_set'), 'images': [str(p) for p in images],
                'missing_images': [str(p) for p in images if not p.is_file()],
                'borrow_notes': c.get('borrow', c.get('lesson', [])),
                'limitations': c.get('avoid', c.get('limits', [])),
                'review': 'Read catalog claim; visual approval still requires opening actual images'})
        if args.contact:
            if not chosen:
                raise ValueError('No matching cases; contact sheet not produced')
            report['contact_sheets'] = contact(chosen, path.parent, args.contact, args.font)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
