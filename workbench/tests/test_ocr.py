import hashlib
import io
import json
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject, NumberObject

from workbench.storage import Store

ROOT = Path(__file__).resolve().parents[2]
NATIVE = '1. A converter comprising a controller and a bridge configured to measure input current.'


def pdf_fixture(native=True, scans=1):
    writer = PdfWriter()
    if native:
        page = writer.add_blank_page(400, 500)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(f'BT /F1 8 Tf 20 400 Td ({NATIVE}) Tj ET'.encode())
        page[NameObject('/Contents')] = writer._add_object(stream)
    for _ in range(scans):
        page = writer.add_blank_page(400, 500)
        image = DecodedStreamObject()
        image.set_data(bytes([255, 0, 0, 255]))
        image.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Image'), NameObject('/Width'): NumberObject(2), NameObject('/Height'): NumberObject(2), NameObject('/ColorSpace'): NameObject('/DeviceGray'), NameObject('/BitsPerComponent'): NumberObject(8)})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/XObject'): DictionaryObject({NameObject('/Im0'): writer._add_object(image)})})
        stream = DecodedStreamObject()
        stream.set_data(b'q 400 0 0 500 0 0 cm /Im0 Do Q')
        page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def recognized(text='1. A converter including an intermittent mode.', score=0.97):
    return {'text': text, 'confidence': score, 'lines': [{'text': text, 'confidence': score, 'box': [[0, 0], [100, 0], [100, 20], [0, 20]]}]}


class OCRTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / 'workbench/ocr.py').is_file(), 'Local OCR is not implemented')
        from workbench import ocr
        self.module = ocr
        self.cache = ROOT / 'workbench-data/test-runs' / uuid.uuid4().hex / 'cache'
        self.availability = patch.object(ocr, 'available', return_value=True)
        self.availability.start()
        self.addCleanup(self.availability.stop)

    def test_mixed_pdf_keeps_native_text_and_original_page_numbers(self):
        with patch.object(self.module, '_recognize_page', return_value=recognized()) as recognize:
            result = self.module.recognize_pdf(pdf_fixture(), self.cache)
        self.assertEqual(result['pages'][0]['text'].strip(), NATIVE)
        self.assertEqual([p['method'] for p in result['pages']], ['native', 'ocr'])
        self.assertEqual([p['number'] for p in result['pages']], [1, 2])
        self.assertIn('intermittent', result['text'])
        self.assertEqual(recognize.call_count, 1)

    def test_native_pdf_does_not_start_ocr_engine(self):
        with patch.object(self.module, '_recognize_page', side_effect=AssertionError('Native page must not be OCRed')):
            result = self.module.recognize_pdf(pdf_fixture(scans=0), self.cache)
        self.assertEqual(result['status'], 'not_needed')
        self.assertEqual(result['native_pages'], 1)

    def test_corrupt_cache_is_rebuilt(self):
        data = pdf_fixture()
        with patch.object(self.module, '_recognize_page', return_value=recognized()) as recognize:
            self.module.recognize_pdf(data, self.cache)
            next(self.cache.rglob('2.json')).write_text('{broken', encoding='utf-8')
            result = self.module.recognize_pdf(data, self.cache)
        self.assertEqual(recognize.call_count, 2)
        self.assertIn('intermittent', result['text'])

    def test_successful_pages_reuse_cache_and_different_pdf_does_not(self):
        data = pdf_fixture()
        with patch.object(self.module, '_recognize_page', return_value=recognized()) as recognize:
            first = self.module.recognize_pdf(data, self.cache)
            again = self.module.recognize_pdf(data, self.cache)
            self.assertEqual(recognize.call_count, 1)
            self.assertEqual(first['text'], again['text'])
            self.assertTrue(again['pages'][1]['cached'])
            self.module.recognize_pdf(pdf_fixture(scans=2), self.cache)
            self.assertEqual(recognize.call_count, 3)

    def test_page_failure_does_not_discard_other_pages_and_is_retryable(self):
        data = pdf_fixture(scans=2)
        with patch.object(self.module, '_recognize_page', side_effect=[recognized(), RuntimeError('engine failed')]):
            result = self.module.recognize_pdf(data, self.cache)
        self.assertEqual(result['status'], 'partial')
        self.assertIn('intermittent', result['pages'][1]['text'])
        self.assertEqual(result['pages'][2]['method'], 'failed')
        self.assertTrue(any('3' in note and 'engine failed' in note for note in result['notes']))
        with patch.object(self.module, '_recognize_page', return_value=recognized()) as retry:
            result = self.module.recognize_pdf(data, self.cache)
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(retry.call_count, 1)

    def test_low_confidence_and_no_text_are_explicit(self):
        with patch.object(self.module, '_recognize_page', side_effect=[recognized(score=0.55), recognized('', 0)]):
            result = self.module.recognize_pdf(pdf_fixture(scans=2), self.cache)
        self.assertEqual(result['pages'][1]['quality'], 'review')
        self.assertEqual(result['pages'][2]['quality'], 'no_text')
        self.assertTrue(result['notes'])

    def test_missing_engine_keeps_native_text_and_marks_scan(self):
        with patch.object(self.module, 'available', return_value=False):
            result = self.module.recognize_pdf(pdf_fixture(), self.cache)
        self.assertEqual(result['pages'][0]['text'].strip(), NATIVE)
        self.assertEqual(result['status'], 'unavailable')
        self.assertTrue(result['notes'])

    def test_store_backfills_existing_scan_preserves_original_and_marked_status(self):
        store = Store(ROOT / 'workbench-data/test-runs' / uuid.uuid4().hex)
        case = store.create('BR112023019754A2')
        data = pdf_fixture()
        doc = store.import_document(case['id'], data, {'filename': 'marked.pdf', 'role': 'claims', 'country': 'EP', 'language': 'unknown', 'requires_clean_text': True})
        store.update(case['id'], lambda c: c.update(exports=[{'name': 'old.docx'}], exports_stale=False))
        with patch.object(self.module, '_recognize_page', return_value=recognized()):
            store.ocr_case(case['id'])
        after = store.get(case['id'])
        updated = after['documents'][0]
        self.assertEqual(updated['id'], doc['id'])
        self.assertTrue(updated['requires_clean_text'])
        self.assertEqual(updated['language'], 'unknown')
        self.assertEqual(updated['sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual((store.case_dir(case['id']) / updated['local_path']).read_bytes(), data)
        self.assertIn('intermittent', updated['text'])
        self.assertEqual(updated['ocr']['ocr_pages'], 1)
        self.assertTrue(after['exports_stale'])

    def test_modified_original_is_not_ocr_processed(self):
        store = Store(ROOT / 'workbench-data/test-runs' / uuid.uuid4().hex)
        case = store.create('BR112023019754A2')
        doc = store.import_document(case['id'], pdf_fixture(), {'filename': 'source.pdf'})
        (store.case_dir(case['id']) / doc['local_path']).write_bytes(b'changed source')
        with patch.object(self.module, '_recognize_page', side_effect=AssertionError('Changed original must not be read')):
            store.ocr_case(case['id'])
        after = store.get(case['id'])['documents'][0]
        self.assertEqual(after['ocr']['status'], 'failed')
        self.assertTrue(any('SHA256' in note for note in after['notes']))


if __name__ == '__main__':
    unittest.main()
