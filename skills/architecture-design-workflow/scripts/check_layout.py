"""Check declared board geometry and optional PDF paper size; never grade aesthetics."""
import argparse
import json
import math
from pathlib import Path
import sys


def numbers(value, count, positive=False):
    return (isinstance(value, list) and len(value) == count
            and all(isinstance(x, (int, float)) and not isinstance(x, bool)
                    and math.isfinite(x) and (not positive or x > 0) for x in value))


def check(data, base=Path('.'), pdf=None):
    errors, warnings = [], []
    paper = data.get('paper_mm')
    pages = data.get('pages')
    if not numbers(paper, 2, positive=True) or not isinstance(pages, list) or not pages:
        return {'automatic_checks': 'failed', 'errors': ['paper_mm and nonempty pages are required'],
                'warnings': [], 'visual_review': 'not assessed', 'user_acceptance': 'not assessed'}
    w, h = paper
    seen = set()
    for page_no, page in enumerate(pages, 1):
        items = page.get('items', [])
        valid = []
        local_ids = set()
        for it in items:
            iid = it.get('id')
            if not isinstance(iid, str) or not iid or iid in local_ids:
                errors.append(f'page {page_no}: missing/duplicate item id {iid!r}')
                continue
            local_ids.add(iid)
            seen.add(iid)
            rect = it.get('rect_mm')
            label = f'page {page_no}/{iid}'
            if not numbers(rect, 4) or rect[2] <= 0 or rect[3] <= 0:
                errors.append(label + ': invalid rect_mm')
                continue
            x, y, iw, ih = rect
            if min(x, y) < -.05 or x+iw > w+.05 or y+ih > h+.05:
                errors.append(label + ': outside paper')
            valid.append(it)
            source = it.get('source')
            if source:
                path = Path(source)
                if not (path if path.is_absolute() else base/path).is_file():
                    errors.append(label + ': source file missing')
            expected = data.get('expected_revision')
            if expected and it.get('revision') and it['revision'] != expected:
                errors.append(label + ': source revision mismatch')
            if expected and not it.get('revision'):
                warnings.append(label + ': revision undeclared')
            minimum = data.get('min_text_mm')
            if it.get('role') in ('text', 'caption') and minimum is not None:
                actual = it.get('text_height_mm')
                if not isinstance(actual, (int, float)) or actual <= 0:
                    warnings.append(label + ': actual printed text height undeclared')
                elif actual < minimum:
                    errors.append(label + ': text below project minimum')
            # Frame includes the same annotation margins in source and destination.
            frame = it.get('source_frame_mm')
            if frame is not None:
                if not numbers(frame, 2, positive=True):
                    errors.append(label + ': invalid source_frame_mm')
                    continue
                sw, sh = frame
                rotation = it.get('rotation', 0) % 360
                if rotation in (90, 270):
                    sw, sh = sh, sw
                elif rotation not in (0, 180):
                    errors.append(label + ': arbitrary rotation needs manual scale validation')
                    continue
                fx, fy = iw/sw, ih/sh
                if abs(fx/fy-1) > .005:
                    errors.append(label + ': anisotropic drawing scaling')
                source_scale, claim = it.get('source_scale'), it.get('claimed_scale')
                if source_scale is not None and claim is not None:
                    if not all(isinstance(n, (int, float)) and n > 0 for n in (source_scale, claim)):
                        errors.append(label + ': scales must be positive')
                    elif abs((source_scale/fx)/claim-1) > .005:
                        errors.append(label + ': claimed scale disagrees with placement')
            elif it.get('claimed_scale'):
                warnings.append(label + ': scale not checked; registered source frame missing')
            pixels = it.get('pixels_after_crop')
            if pixels is not None:
                if not numbers(pixels, 2, positive=True):
                    errors.append(label + ': invalid pixels_after_crop')
                else:
                    ppi = min(pixels[0]/(iw/25.4), pixels[1]/(ih/25.4))
                    threshold = data.get('min_raster_ppi')
                    if threshold and ppi < threshold:
                        warnings.append(label + f': raster PPI {ppi:.1f} below project target {threshold}')
        for i, a in enumerate(valid):
            for b in valid[i+1:]:
                # Intentional masks, overlays, captions within image: declare pair explicitly.
                if b['id'] in a.get('allow_overlap_with', []) or a['id'] in b.get('allow_overlap_with', []):
                    continue
                ax, ay, aw, ah = a['rect_mm']; bx, by, bw, bh = b['rect_mm']
                dx, dy = min(ax+aw,bx+bw)-max(ax,bx), min(ay+ah,by+bh)-max(ay,by)
                if dx > .1 and dy > .1:
                    errors.append(f'page {page_no}: undeclared overlap {a["id"]}/{b["id"]}')
        fraction = page.get('hero_min_fraction')
        if fraction is not None:
            if not isinstance(fraction, (int, float)) or not 0 < fraction <= 1:
                errors.append(f'page {page_no}: invalid hero_min_fraction')
            else:
                heroes = [it['rect_mm'][2]*it['rect_mm'][3] for it in valid if it.get('role') == 'hero']
                if not heroes or max(heroes) < w*h*fraction:
                    errors.append(f'page {page_no}: main image below project fraction')
    missing = set(data.get('required_items', [])) - seen
    if missing:
        errors.append('missing required items: ' + ', '.join(sorted(missing)))
    if pdf:
        try:
            import pymupdf as fitz
            with fitz.open(pdf) as document:
                if len(document) != len(pages):
                    errors.append('PDF page count differs from layout')
                for i, p in enumerate(document):
                    actual = [p.rect.width*25.4/72, p.rect.height*25.4/72]
                    if any(abs(a-b) > .2 for a,b in zip(actual,paper)):
                        errors.append(f'PDF page {i+1}: paper size/orientation mismatch')
        except (ImportError, OSError, RuntimeError) as exc:
            errors.append('PDF paper check unavailable: ' + str(exc))
    return {'automatic_checks': 'failed' if errors else 'passed', 'errors': errors,
            'warnings': warnings, 'checked': 'declared geometry; optional actual PDF page dimensions',
            'visual_review': 'not assessed', 'model_fidelity': 'not assessed',
            'psd_editability': 'not assessed', 'user_acceptance': 'not assessed'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('layout', type=Path)
    parser.add_argument('--pdf', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    try:
        result = check(json.loads(args.layout.read_text(encoding='utf-8-sig')), args.layout.parent, args.pdf)
    except (OSError, ValueError, TypeError) as exc:
        result = {'automatic_checks': 'failed', 'errors': [str(exc)], 'visual_review': 'not assessed'}
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text+'\n', encoding='utf-8')
    print(text)
    return 2 if result['automatic_checks'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
