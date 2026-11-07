"""Offline regression tests: actual geometry invariants and local image handling."""
import json
from pathlib import Path
import tempfile
import unittest

from cases import contact, load_cases, select
from check_layout import check
from resources import command


def valid_layout():
    return {'paper_mm': [594,841], 'required_items': ['main','plan','title'],
            'min_text_mm': 2.5,
            'pages': [{'hero_min_fraction': 1/3, 'items': [
                {'id':'main','role':'hero','rect_mm':[8,8,578,296]},
                {'id':'plan','rect_mm':[8,330,240,280], 'source_frame_mm':[240,280],
                 'source_scale':300, 'claimed_scale':300},
                {'id':'title','role':'caption','rect_mm':[8,615,240,7], 'text_height_mm':5}]}]}


class LayoutTests(unittest.TestCase):
    def test_true_scale_layout_does_not_claim_aesthetic_or_host_acceptance(self):
        r=check(valid_layout())
        self.assertEqual(r['automatic_checks'],'passed')
        self.assertEqual(r['visual_review'],'not assessed')
        self.assertEqual(r['psd_editability'],'not assessed')

    def test_moved_title_collision_is_detected(self):
        d=valid_layout();d['pages'][0]['items'][2]['rect_mm'][1]=605
        self.assertTrue(any('overlap' in e for e in check(d)['errors']))

    def test_annotated_overlay_can_be_explicitly_allowed(self):
        d=valid_layout();d['pages'][0]['items'][2]['rect_mm'][1]=605
        d['pages'][0]['items'][2]['allow_overlap_with']=['plan']
        self.assertFalse(check(d)['errors'])

    def test_anisotropic_stretch_and_false_scale_detected(self):
        d=valid_layout();d['pages'][0]['items'][1]['rect_mm'][2]=120
        errors=check(d)['errors']
        self.assertTrue(any('anisotropic' in e for e in errors))
        self.assertTrue(any('claimed scale' in e for e in errors))

    def test_uniform_half_size_requires_double_denominator(self):
        d=valid_layout();it=d['pages'][0]['items'][1]
        it['rect_mm'][2:]=[120,140];it['claimed_scale']=600
        self.assertFalse(check(d)['errors'])

    def test_rotation_swaps_registered_frame(self):
        d=valid_layout();it=d['pages'][0]['items'][1]
        it.update(rotation=90,rect_mm=[8,330,280,240])
        self.assertFalse(check(d)['errors'])

    def test_paper_overflow_missing_drawing_and_small_text_detected(self):
        d=valid_layout();d['required_items'].append('section')
        d['pages'][0]['items'][2].update(rect_mm=[590,615,20,7],text_height_mm=1)
        errors=' '.join(check(d)['errors'])
        for word in ['outside paper','missing required','text below']:
            self.assertIn(word,errors)

    def test_insufficient_hero_and_revision_mismatch(self):
        d=valid_layout();d['pages'][0]['items'][0]['rect_mm'][2]=200
        d['expected_revision']='R2';d['pages'][0]['items'][1]['revision']='R1'
        errors=' '.join(check(d)['errors'])
        self.assertIn('main image below',errors);self.assertIn('revision mismatch',errors)

    def test_unknown_scale_is_not_silently_verified(self):
        d=valid_layout();del d['pages'][0]['items'][1]['source_frame_mm']
        self.assertTrue(any('scale not checked' in w for w in check(d)['warnings']))

    def test_real_pdf_orientation_mismatch(self):
        import pymupdf as fitz
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'board.pdf';q=fitz.open();q.new_page(width=841*72/25.4,height=594*72/25.4)
            q.save(path);q.close()
            self.assertTrue(any('orientation' in e for e in check(valid_layout(),pdf=path)['errors']))


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.rows=[{'case_id':'CASE_01','category':'竖向 景观','complete_set':True},
                   {'case_id':'CASE_02','category':'竖向','complete_set':False},
                   {'case_id':'CASE_03','category':'竖向','status':'排除'}]

    def test_query_filters_and_explicit_identity(self):
        self.assertEqual([c['case_id'] for c in select(self.rows,'景观',complete=True)],['CASE_01'])
        self.assertEqual(len(select(self.rows)),2)
        self.assertEqual(select(self.rows,ids=['CASE_03'])[0]['case_id'],'CASE_03')
        with self.assertRaises(ValueError):select(self.rows,ids=['UNKNOWN'])

    def test_duplicate_record_ids_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'index.json';p.write_text(json.dumps({'cases':[self.rows[0],self.rows[0]]}),encoding='utf-8')
            with self.assertRaises(ValueError):load_cases(p)

    def test_contact_sheet_preserves_entire_portrait_and_landscape(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            for name,size in [('portrait',(100,400)),('landscape',(400,100))]:
                im=Image.new('RGB',size,'white')
                im.paste('red',(0,0,size[0],8));im.paste('blue',(0,size[1]-8,size[0],size[1]));im.save(base/(name+'.png'))
            row={'case_id':'TEST','display_images':['portrait.png','landscape.png']}
            result=contact([row],base,base/'contact.png')
            self.assertEqual(len(result),1)
            with Image.open(result[0]) as im:
                left=im.crop((0,0,300,390));right=im.crop((300,0,600,390))
                for tile in [left,right]:
                    colors=[tile.getpixel((x,y)) for y in range(tile.height) for x in range(tile.width)]
                    self.assertTrue(any(r>180 and g<80 and b<80 for r,g,b in colors))
                    self.assertTrue(any(b>180 and r<80 and g<80 for r,g,b in colors))

    def test_missing_image_does_not_claim_generated_contact(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                contact([{'case_id':'TEST','display_images':['missing.png']}],Path(folder),Path(folder)/'x.png')


class ResourceTests(unittest.TestCase):
    def test_existing_tools_receive_bound_roots_and_explicit_read_only_modes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in ['design/scripts/search_cases.py','design/index/cases.json',
                         'repo/tools/engineering_assets/find_asset.py','repo/knowledge/engineering-assets/catalog.json',
                         'repo/tools/revit_assets/library.py','native/database/revit-assets.sqlite']:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}',encoding='utf-8')
            cfg={'design_case_root':str(root/'design'),'workflow_repo':str(root/'repo'),
                 'engineering_catalog':str(root/'repo/knowledge/engineering-assets/catalog.json'),
                 'revit_database':str(root/'native/database/revit-assets.sqlite')}
            a=command(cfg,'design','中庭',mode='lexical')
            self.assertIn('baseline',a);self.assertIn('--keyword',a);self.assertNotIn('--query',a)
            a=command(cfg,'engineering','切墙',software='revit')
            self.assertIn('--software',a);self.assertNotIn('collect-local',a)
            with self.assertRaises(ValueError):command(cfg,'revit','窗')
            a=command(cfg,'revit','窗',revit=2021,asset_kind='family')
            self.assertIn('search',a);self.assertIn('2021',a);self.assertNotIn('stage',a)
            self.assertEqual(Path(a[a.index('--root')+1]),(root/'native').resolve())

    def test_missing_library_is_not_created_and_unrelated_catalog_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);missing=root/'missing.sqlite'
            with self.assertRaises(ValueError):
                command({'workflow_repo':str(root),'revit_database':str(missing)},'revit','窗',revit=2021)
            self.assertFalse(missing.exists())
            other=root/'other.json';other.write_text('{}',encoding='utf-8')
            with self.assertRaises(ValueError):
                command({'workflow_repo':str(root),'engineering_catalog':str(other)},'engineering','门')


if __name__=='__main__':
    unittest.main(verbosity=2)
