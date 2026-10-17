"""Regression checks for the downloaded/OCR evidence -> drafting handoff."""
import copy
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from workbench.analysis import analyze_case
from workbench.drafting import generate_package
from workbench.ocr import cache_version
from workbench.storage import Store
from workbench.tests.test_ocr import pdf_fixture

ROOT = Path(__file__).resolve().parents[2]
CLAIMS = (
    '1. A converter comprising a controller configured to measure the input current and the output current, '
    'wherein the controller is configured to control the bridge according to the current measured by the '
    'controller, and wherein the bridge is connected to the input and the output of the converter.\n'
    '2. The converter according to claim 1, wherein the controller is configured to operate in an intermittent '
    'mode, and wherein the input of the controller is connected to a sensor for the input current and a '
    'sensor for the output current, the sensors being configured to measure the current of the converter.'
)
REPLY = (
    'The applicant submits that the cited document does not disclose the controller of claim 1. '
    'The amended claims define the controller configured to measure the input current and the output current. '
    'This is the basis for the inventive step of the claimed converter. The method of the cited document '
    'does not have the intermittent mode of the claimed device, and the application describes the control '
    'of the bridge in the intermittent mode. The applicant requests examination of the amended claims '
    'and reconsideration of the objection in view of the above arguments and the amended claim 1.'
)


class MetadataHandoffTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(ROOT / 'workbench-data/test-runs' / uuid.uuid4().hex)
        self.case_id = self.store.create('BR112023019754A2')['id']
        self.reply = self.add('Amendments received before examination', 'response', REPLY)
        self.claims = self.add('Amended claims filed after receipt of (European) search report', 'claims', CLAIMS)
        self.store.update(self.case_id, lambda c: c.update(cycles=[{
            'application': 'EP21934362', 'response_id': self.reply['id'],
            'source_url': 'https://register.epo.org/application?number=EP21934362&tab=doclist',
            'pairing_status': 'date-based candidate; source content still controls'}]))

    def add(self, title, role, text, **extra):
        meta = dict(filename=title + '.txt', title=title, role=role, country='EP',
                    application='EP21934362', date='2025-05-09', language='unknown')
        meta.update(extra)
        return self.store.import_document(self.case_id, text.encode('utf-8'), meta)

    def processed(self):
        # No engine/network calls should be needed for existing extracted text.
        with patch('workbench.ocr.recognize_pdf', side_effect=AssertionError('OCR must be cached')):
            return self.store.ocr_case(self.case_id)

    def test_extracted_english_body_is_identified_with_inference_evidence(self):
        current = self.processed()
        doc = next(d for d in current['documents'] if d['id'] == self.reply['id'])
        self.assertEqual(doc['language'], 'en')
        self.assertEqual(doc['metadata_inference']['language']['method'], 'body_vocabulary_v1')
        self.assertGreater(doc['metadata_inference']['language']['token_count'], 80)

    def test_complete_cycle_becomes_usable_without_fabricating_target_sources(self):
        current = self.processed()
        sources = analyze_case(current)['sources']
        self.assertIsNotNone(sources['claims'], 'Downloaded clean cycle claims never reached drafting')
        self.assertEqual(sources['claims']['id'], self.claims['id'])
        self.assertEqual(sources['response']['id'], self.reply['id'])
        self.assertEqual(sources['claims']['version_status'], 'reference')
        self.assertEqual(sources['claims']['cycle_id'], sources['response']['cycle_id'])
        self.assertIn('date', sources['claims']['metadata_inference']['cycle_id']['method'])
        self.assertTrue(all(sources[key] is None for key in ('oa', 'pending', 'original')))

    def test_cached_ocr_also_repairs_metadata_and_generated_package_has_source_text(self):
        scan = self.store.import_document(self.case_id, pdf_fixture(native=False),
            dict(filename='cached.pdf', title='Cached English source', role='other', language='unknown'))
        def cache(case):
            doc = next(d for d in case['documents'] if d['id'] == scan['id'])
            doc.update(text=REPLY, pages=[{'number': 1, 'text': REPLY}],
                       ocr={'status': 'complete', 'version': cache_version()})
            case.update(exports=[{'name': 'old.docx'}], exports_stale=False)
        self.store.update(self.case_id, cache)
        current = self.processed()
        cached = next(d for d in current['documents'] if d['id'] == scan['id'])
        self.assertEqual(cached['language'], 'en')
        self.assertTrue(current['exports_stale'])
        out = self.store.case_dir(self.case_id) / 'outputs'
        generated = generate_package(current, out, self.store.case_dir(self.case_id))
        self.assertEqual(generated['analysis']['sources']['claims']['id'], self.claims['id'])
        self.assertIn('The applicant submits that', (out / '03-意见陈述书.html').read_text(encoding='utf-8'))
        self.assertIn('intermittent', (out / '05-修改后权利要求清洁稿.html').read_text(encoding='utf-8'))
        self.assertFalse(generated['analysis']['baseline_usable'])

    def test_foreign_body_with_english_heading_or_chinese_cover_is_not_english(self):
        french = self.add('English amended claims', 'claims', 'European Patent Office\n' +
            ('Le dispositif selon la revendication dans lequel les capteurs et le controleur sont '
             'connectes pour une mesure du courant dans les circuits de la presente invention. ' * 12))
        german = self.add('English translation of claims', 'claims', 'European Patent Office\n' +
            ('Der Wandler nach Anspruch mit einer Steuerung und den Sensoren, die mit dem Eingang '
             'und dem Ausgang des Wandlers verbunden sind und dadurch gekennzeichnet werden. ' * 12))
        chinese = self.add('English search report', 'oa', REPLY + ('本发明涉及一种变换器的控制方法和控制电路。' * 150))
        short = self.add('English claims', 'claims', '1. A converter.')
        current = self.processed()
        by_id = {d['id']: d for d in current['documents']}
        for doc in (french, german, chinese, short):
            self.assertEqual(by_id[doc['id']]['language'], 'unknown')

    def test_explicit_user_metadata_is_preserved_including_unknown(self):
        self.store.edit_document(self.case_id, self.reply['id'], {'language': 'unknown', 'cycle_id': 'user-cycle'})
        self.store.edit_document(self.case_id, self.claims['id'], {'version_status': 'unknown'})
        current = self.processed()
        by_id = {d['id']: d for d in current['documents']}
        self.assertEqual(by_id[self.reply['id']]['language'], 'unknown')
        self.assertEqual(by_id[self.reply['id']]['cycle_id'], 'user-cycle')
        self.assertEqual(by_id[self.claims['id']]['version_status'], 'unknown')
        self.assertIsNone(analyze_case(current)['sources']['claims'])

    def test_marked_and_auxiliary_versions_are_not_promoted_to_clean_reference(self):
        marked = self.add('Amended claims with annotations', 'claims', CLAIMS, requires_clean_text=True)
        auxiliary = self.add('Auxiliary claims', 'claims', CLAIMS, version_status='auxiliary')
        grant_text = self.add('Text intended for grant (clean copy)', 'other', CLAIMS)
        current = self.processed()
        by_id = {d['id']: d for d in current['documents']}
        self.assertTrue(by_id[marked['id']]['requires_clean_text'])
        self.assertEqual(by_id[marked['id']]['version_status'], 'unknown')
        self.assertEqual(by_id[auxiliary['id']]['version_status'], 'auxiliary')
        self.assertEqual(by_id[grant_text['id']]['role'], 'other')
        self.assertIsNotNone(analyze_case(current)['sources']['claims'])
        self.assertEqual(analyze_case(current)['sources']['claims']['id'], self.claims['id'])

    def test_cycle_link_does_not_cross_application_or_date_and_is_idempotent(self):
        other = self.add('Amended claims', 'claims', CLAIMS, application='EP22123456')
        earlier = self.add('Earlier amended claims', 'claims', CLAIMS, date='2024-05-09')
        current = self.processed()
        by_id = {d['id']: d for d in current['documents']}
        for doc in (other, earlier):
            self.assertFalse(by_id[doc['id']].get('cycle_id'))
            self.assertEqual(by_id[doc['id']]['version_status'], 'unknown')
        snapshot = copy.deepcopy(current['documents'])
        self.assertEqual(self.processed()['documents'], snapshot)

    def test_maintenance_is_not_a_substantive_response_unless_user_classified_it(self):
        admin = self.add('Maintenance of the application', 'response', REPLY, date='2026-05-09')
        invitation = self.add('Invitation to declare maintenance of the application', 'oa', REPLY)
        user = self.add('Maintenance of the application', 'response', REPLY)
        self.store.edit_document(self.case_id, user['id'], {'role': 'response'})
        current = self.processed()
        by_id = {d['id']: d for d in current['documents']}
        self.assertEqual(by_id[admin['id']]['role'], 'other')
        self.assertEqual(by_id[invitation['id']]['role'], 'other')
        self.assertEqual(by_id[user['id']]['role'], 'response')
        self.assertEqual(analyze_case(current)['sources']['response']['id'], self.reply['id'])


if __name__ == '__main__':
    unittest.main()
