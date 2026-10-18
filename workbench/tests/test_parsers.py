import copy
import importlib
import io
import json
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from workbench.analysis import document_text
from workbench.storage import Store
from workbench.tests.test_ocr import pdf_fixture

ROOT = Path(__file__).resolve().parents[2]


class ParserTests(unittest.TestCase):
    def test_local_default_does_not_affect_other_data_directories(self):
        parser=self.parser();root=ROOT/'workbench-data/test-runs'/uuid.uuid4().hex
        (root/'tools').mkdir(parents=True)
        (root/'tools/default-parser.json').write_text('{"engine":"docling_tesseract"}',encoding='utf-8')
        with patch.object(parser,'backend_status',return_value=[dict(id='docling_tesseract',installed=True)]):
            self.assertEqual(Store(root).create('BR112023019754A2')['settings']['ocr_engine'],'docling_tesseract')
            self.assertEqual(Store(root/'other').create('BR112023019754A2')['settings']['ocr_engine'],'rapidocr')
    def test_docling_adapter_preserves_original_claim_markers(self):
        from workbench.ocr_worker import docling_layout
        payload=dict(pages={'1':dict(size=dict(width=600,height=840))},
            texts=[dict(self_ref='#/texts/0',label='list_item',text='A converter.',marker='5.',
                orig='5. A converter.',prov=[dict(page_no=1,bbox=dict(l=50,t=700,r=500,b=670,coord_origin='BOTTOMLEFT'))])],
            body=dict(children=[{'$ref':'#/texts/0'}]))
        result=docling_layout(payload)
        self.assertEqual(result['body_text'],'5. A converter.')
        self.assertEqual(result['text'],'5. A converter.')
        self.assertEqual(result['pages'][0]['blocks'][0]['bbox'],[50,140,500,170])

    def test_docling_cross_page_segments_and_table_cells_are_kept_once(self):
        from workbench.ocr_worker import docling_layout
        box=dict(l=50,t=700,r=500,b=670,coord_origin='BOTTOMLEFT')
        payload=dict(pages={str(p):dict(size=dict(width=600,height=840)) for p in (1,2)},
            texts=[dict(self_ref='#/texts/0',label='text',text='First page. Next page.',
                prov=[dict(page_no=1,bbox=box,charspan=[0,11]),dict(page_no=2,bbox=box,charspan=[12,22])])],
            tables=[dict(self_ref='#/tables/0',label='table',data=dict(table_cells=[dict(text='10 A maximum')]),
                prov=[dict(page_no=2,bbox=box)])],body=dict(children=[{'$ref':'#/texts/0'},{'$ref':'#/tables/0'}]))
        result=docling_layout(payload)
        self.assertEqual(result['body_text'].count('First page.'),1)
        self.assertEqual(result['body_text'].count('Next page.'),1)
        self.assertIn('10 A maximum',result['body_text'])

    def test_raw_ocr_covers_empty_table_and_unassigned_lines(self):
        from workbench.ocr_worker import supplement_page
        parser=self.parser()
        page=parser.normalize_layout([dict(page=1,text='Title',label='text',bbox=[50,10,500,30]),
            dict(page=1,text='',label='table',bbox=[50,100,500,200])],{1:dict(width=600,height=840)})['pages'][0]
        supplement_page(page,[dict(text='Title',bbox=[50,10,200,30]),dict(text='10 A maximum',bbox=[60,110,300,130]),
            dict(text='outside layout',bbox=[60,250,300,270])])
        self.assertIn('10 A maximum',page['body_text'])
        self.assertIn('outside layout',page['body_text'])
        self.assertEqual(len(page['ocr_lines']),3)

    def test_unassigned_ocr_line_keeps_its_geometric_position(self):
        from workbench.ocr_worker import supplement_page
        page=self.parser().normalize_layout([dict(page=1,text='Before',label='text',bbox=[50,10,500,30]),
            dict(page=1,text='After',label='text',bbox=[50,300,500,330])],{1:dict(width=600,height=840)})['pages'][0]
        supplement_page(page,[dict(text='Before',bbox=[50,10,100,30]),dict(text='Middle',bbox=[50,250,100,270]),
            dict(text='After',bbox=[50,300,100,330])])
        self.assertEqual(page['body_text'],'Before\nMiddle\nAfter')

    def test_letter_contact_column_is_excluded_without_losing_argument(self):
        blocks=[dict(page=1,text=t,label='text',bbox=b) for t,b in [
            ('Firm address',[50,40,350,60]),('In response to the search opinion:',[50,200,420,240]),
            ('The current is not greater than 5 A.',[50,250,420,280]),
            ('www.example.org Patent Attorneys',[460,100,550,130]),('Lawyer name',[460,250,550,280])]]
        result=self.parser().normalize_layout(blocks,{1:dict(width=600,height=840)})
        self.assertEqual(result['body_text'],'In response to the search opinion:\nThe current is not greater than 5 A.')
        self.assertIn('Lawyer name',result['text'])

    def test_sparse_gutter_sequence_does_not_become_claim_number(self):
        blocks=[dict(page=1,text=str(n),label='text',bbox=[40,100+i*50,50,110+i*50]) for i,n in enumerate((10,20,25,30))]
        blocks.append(dict(page=1,text='1. A converter with 10 switches.',label='text',bbox=[90,90,500,250]))
        result=self.parser().normalize_layout(blocks,{1:dict(width=600,height=840)})
        self.assertEqual(result['body_text'],'1. A converter with 10 switches.')

    def test_page_fraction_does_not_remove_bottom_technical_text(self):
        blocks=[dict(page=1,text=t,label=label,bbox=b) for t,label,b in [
            ('Claims','section_header',[200,60,400,80]),('1. A converter.','text',[50,100,550,130]),
            ('wherein the current is not greater than 5 A.','text',[50,765,550,785]),
            ('1 / 4','text',[270,815,330,830])]]
        result=self.parser().normalize_layout(blocks,{1:dict(width=600,height=840)})
        self.assertIn('not greater than 5 A.',result['body_text'])
        self.assertNotIn('1 / 4',result['body_text'])
    def parser(self):
        self.assertTrue((ROOT / 'workbench/parsers.py').is_file(), 'Alternative parsers not connected')
        return importlib.import_module('workbench.parsers')

    def test_layout_removes_only_identified_furniture_and_margin_counters(self):
        parser = self.parser()
        blocks = [
            dict(page=1, text='Law firm header', label='page_header', bbox=[50, 10, 500, 30]),
            dict(page=1, text='5', label='text', bbox=[20, 110, 30, 122]),
            dict(page=1, text='10', label='text', bbox=[20, 160, 30, 172]),
            dict(page=1, text='15', label='text', bbox=[20, 210, 30, 222]),
            dict(page=1, text='1. A converter having 5 coils and 10 switches.', label='text', bbox=[90, 110, 500, 140]),
            dict(page=1, text='2. The converter of claim 1, wherein the current is not greater than 5 A.', label='text', bbox=[90, 150, 500, 190]),
            dict(page=1, text='10', label='text', bbox=[90, 200, 110, 210]),
            dict(page=1, text='- 1/2 -', label='page_footer', bbox=[270, 800, 330, 820])]
        result = parser.normalize_layout(blocks, {1: {'width':600, 'height':840}})
        self.assertIn('Law firm header', result['text'])
        self.assertNotIn('Law firm header', result['body_text'])
        self.assertIn('5 coils and 10 switches', result['body_text'])
        self.assertIn('not greater than 5 A', result['body_text'])
        self.assertTrue(result['body_text'].endswith('10'))
        self.assertEqual(len(result['pages'][0]['excluded_blocks']), 5)
        self.assertEqual(result['pages'][0]['excluded_blocks'][1]['reason'], 'left_margin_line_number')

    def test_isolated_numbers_and_semantic_claim_markers_are_preserved(self):
        blocks=[dict(page=1,text='5',label=label,bbox=[20,100,30,112]) for label in ('list_item','text')]
        result=self.parser().normalize_layout(blocks,{1:dict(width=600,height=840)})
        self.assertEqual(result['body_text'],'5\n5')
        self.assertEqual(result['pages'][0]['excluded_blocks'],[])

    def test_failed_rapidocr_switch_preserves_active_body_and_pages(self):
        store=Store(ROOT/'workbench-data/test-runs'/uuid.uuid4().hex)
        case=store.create('BR112023019754A2')
        store.import_document(case['id'],pdf_fixture(native=False),dict(filename='claims.pdf',role='claims',country='EP',language='en'))
        def setup(c):
            c['documents'][0].update(text='Header\n1. Prior wording.',draft_text='1. Prior wording.',
                pages=[dict(number=1,text='Prior page')],ocr=dict(version='alternative',status='complete'))
        store.update(case['id'],setup)
        for status in ('partial','unavailable'):
            result=dict(text='',pages=[dict(number=1,text='')],status=status,notes=['OCR：unavailable'],version='failed')
            with patch('workbench.ocr.recognize_pdf',return_value=result):store.ocr_case(case['id'])
            after=store.get(case['id'])['documents'][0]
            self.assertEqual(after['draft_text'],'1. Prior wording.')
            self.assertEqual(after['pages'][0]['text'],'Prior page')
            self.assertTrue(after['ocr']['active_text_preserved'])

    def test_coordinate_cleanup_preserves_claim_numbers_and_supports_multiple_pages(self):
        parser = self.parser()
        blocks = [dict(page=p,text=t,label='text',bbox=[15,100,500,150]) for p,t in
                  [(1,'1. A converter.'),(2,'2. The converter of claim 1.')]]
        snapshot = copy.deepcopy(blocks)
        result = parser.normalize_layout(blocks, {p:{'width':600,'height':840} for p in (1,2)})
        self.assertEqual(blocks,snapshot)
        self.assertEqual([p['number'] for p in result['pages']],[1,2])
        self.assertIn('1. A converter.',result['body_text'])

    def test_backend_cache_identity_and_unknown_backend_rejection(self):
        parser = self.parser()
        self.assertNotEqual(parser.backend_version('docling_tesseract'),parser.backend_version('paddle_structure'))
        with self.assertRaises(ValueError): parser.backend_version('../../untrusted')

    def test_successful_parser_result_reuses_cache_and_preserves_original_bytes(self):
        parser = self.parser(); root=ROOT/'workbench-data/test-runs'/uuid.uuid4().hex
        data=pdf_fixture(native=False)
        result=dict(text='1. A converter.',body_text='1. A converter.',pages=[dict(number=1,text='1. A converter.',body_text='1. A converter.',method='ocr',quality='review')],notes=[],status='complete',ocr_pages=1,native_pages=0,failed_pages=[],review_pages=[1],empty_pages=[])
        with patch.object(parser,'run_worker',return_value=result) as worker, patch.object(parser,'crosscheck_document',side_effect=lambda data,cache,result:result):
            one=parser.recognize_document(data,root,'docling_tesseract')
            two=parser.recognize_document(data,root,'docling_tesseract')
        self.assertEqual(worker.call_count,1)
        self.assertEqual(one['body_text'],two['body_text'])
        self.assertTrue(two['cache_hit'])

    def test_missing_claim_reference_is_flagged_without_guessing_a_number(self):
        parser=self.parser()
        result=parser.normalize_layout([dict(page=1,text='The device according to claim',label='text',bbox=[50,100,500,130])],{1:dict(width=600,height=840)})
        baseline=dict(status='complete',version='baseline-version',text='The device according to claim 3;',
            pages=[dict(number=1,text='The device according to claim 3;',image_size=[600,840],
                lines=[dict(text='The device according to claim 3;',box=[[50,100],[500,100],[500,130],[50,130]])])])
        with patch('workbench.ocr.recognize_pdf',return_value=baseline):
            checked=parser.crosscheck_document(b'pdf',ROOT,result)
        self.assertEqual(checked['crosscheck']['status'],'disagreement')
        self.assertIn('3;',checked['body_text'])
        self.assertNotIn('3;',checked['parser_body_text'])
        self.assertEqual(checked['crosscheck']['body_source'],'rapidocr_with_docling_layout')

    def test_comparison_and_negative_sign_disagreements_are_flagged(self):
        parser=self.parser()
        for baseline_text in ('current is < 5 A.','current is -5 A.'):
            result=parser.normalize_layout([dict(page=1,text='current is 5 A.',label='text',bbox=[50,100,500,130])],{1:dict(width=600,height=840)})
            baseline=dict(status='complete',version='baseline',text=baseline_text,pages=[dict(number=1,
                image_size=[600,840],lines=[dict(text=baseline_text,box=[[50,100],[500,100],[500,130],[50,130]])])])
            with patch('workbench.ocr.recognize_pdf',return_value=baseline):
                checked=parser.crosscheck_document(b'pdf',ROOT,result)
            self.assertEqual(checked['crosscheck']['status'],'disagreement')
            self.assertEqual(checked['body_text'],baseline_text)

    def test_drafting_prefers_derived_body_while_original_text_remains_available(self):
        doc=dict(text='Header\n1. A converter.\nFooter',draft_text='1. A converter.')
        self.assertEqual(document_text(doc),'1. A converter.')
        self.assertIn('Header',doc['text'])

    def test_failed_alternative_parser_keeps_existing_text_and_archives_on_success(self):
        parser=self.parser();store=Store(ROOT/'workbench-data/test-runs'/uuid.uuid4().hex)
        case=store.create('BR112023019754A2')
        doc=store.import_document(case['id'],pdf_fixture(native=False),dict(filename='claims.pdf',role='claims',country='EP',language='en'))
        from workbench.ocr import cache_version
        def setup(c):
            c['settings']['ocr_engine']='docling_tesseract'
            c['documents'][0].update(text='1. Prior verified wording.',pages=[{'number':1,'text':'1. Prior verified wording.'}],ocr={'version':cache_version(),'status':'complete'})
        store.update(case['id'],setup)
        with patch.object(parser,'recognize_document',side_effect=RuntimeError('worker failed')):
            store.ocr_case(case['id'])
        failed=store.get(case['id'])['documents'][0]
        self.assertEqual(failed['text'],'1. Prior verified wording.')
        self.assertEqual(failed['ocr']['status'],'failed')
        result=dict(text='Header\n1. Improved converter.',body_text='1. Improved converter.',pages=[dict(number=1,text='Header\n1. Improved converter.',body_text='1. Improved converter.',method='ocr',quality='review')],notes=[],status='complete',version=parser.backend_version('docling_tesseract'),ocr_pages=1,native_pages=0)
        with patch.object(parser,'recognize_document',return_value=result):store.ocr_case(case['id'])
        after=store.get(case['id'])['documents'][0]
        self.assertEqual(document_text(after),'1. Improved converter.')
        self.assertTrue(after.get('ocr_history'))
        archives=list((store.case_dir(case['id'])/'derived').glob('*.json'))
        self.assertTrue(any('Prior verified wording' in p.read_text(encoding='utf-8') for p in archives))
        self.assertEqual((store.case_dir(case['id'])/doc['local_path']).read_bytes(),pdf_fixture(native=False))


if __name__=='__main__':unittest.main()
