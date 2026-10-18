import importlib
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from workbench.analysis import analyze_case
from workbench.storage import Store

ROOT = Path(__file__).resolve().parents[2]


class ResearchTests(unittest.TestCase):
    def test_reply_titles_are_not_office_actions(self):
        from workbench.retrieval import classify_document
        for title in ('Reply to examination report', 'Response to non-final rejection', 'Reply to communication under Article 94(3) EPC'):
            self.assertEqual(classify_document(title), 'response')
        self.assertEqual(classify_document('Amended claims filed after receipt of (European) search report'), 'claims')
        self.assertEqual(classify_document('Invitation to declare maintenance of the application and to correct deficiencies in the Written Opinion/amend application'), 'other')

    def test_research_invalidates_previous_exports_even_when_download_fails(self):
        case = self.store.create('BR112023019754A2')
        self.store.update(case['id'], lambda c: c.update(exports=[{'name':'00-完整答复包.zip'}], exports_stale=False))
        self.module.research_case(self.store, case['id'], fetch=lambda url: (_ for _ in ()).throw(OSError('blocked')))
        self.assertTrue(self.store.get(case['id'])['exports_stale'])

    def setUp(self):
        self.assertTrue((ROOT / 'workbench/research.py').exists(), 'Research orchestration is not implemented')
        self.module = importlib.import_module('workbench.research')
        self.store = Store(ROOT / 'workbench-data' / 'test-runs' / uuid.uuid4().hex)

    def test_blocked_network_preserves_import_and_manual_guides(self):
        case = self.store.create('BR112023019754A2')
        doc = self.store.import_document(case['id'], b'1. A converter.', {'filename':'claims.txt','role':'claims','country':'BR','version_status':'pending'})
        def blocked(url, **kwargs):
            raise OSError('HTTP 403 blocked')
        self.module.research_case(self.store, case['id'], fetch=blocked)
        after = self.store.get(case['id'])
        self.assertIn(doc['id'], [d['id'] for d in after['documents']])
        self.assertEqual(after['status'], 'idle')
        self.assertTrue(after['manual_guides'])
        self.assertTrue(any('403' in e['message'] for e in after['events']))

    def test_select_latest_oa_and_prior_complete_cycle(self):
        docs = [
            {'id':'oa-new','date':'2026-05-01','role':'oa','application':'EP123'},
            {'id':'oa-old','date':'2025-01-01','role':'oa','application':'EP123'},
            {'id':'reply','date':'2025-03-01','role':'response','application':'EP123'},
            {'id':'claims','date':'2025-03-01','role':'claims','application':'EP123'},
            {'id':'receipt','date':'2026-06-01','role':'other','application':'EP123'}]
        chosen = self.module.choose_cycle(docs)
        self.assertEqual(chosen['latest_oa']['id'], 'oa-new')
        self.assertEqual(chosen['response']['id'], 'reply')
        self.assertEqual(chosen['response_oa']['id'], 'oa-old')
        self.assertEqual(chosen['claims'][0]['id'], 'claims')

    def test_new_unpaired_response_does_not_hide_older_complete_cycle(self):
        docs = [{'id':'old-oa','date':'2025-01-01','role':'oa','application':'EP123'},
                {'id':'old-reply','date':'2025-03-01','role':'response','application':'EP123'},
                {'id':'old-claims','date':'2025-03-01','role':'claims','application':'EP123'},
                {'id':'new-reply','date':'2026-01-01','role':'response','application':'EP123'}]
        cycle = self.module.choose_cycle(docs)
        self.assertEqual(cycle['response']['id'], 'old-reply')

    def test_research_ingestion_does_not_pair_new_response_with_old_claims(self):
        case = self.store.create('BR112023019754A2')
        entries = [('old-oa', '01.01.2025', 'Communication under Article 94'),
                   ('old-reply', '01.03.2025', 'Response'),
                   ('old-claims', '01.03.2025', 'Claims'),
                   ('new-oa', '01.06.2025', 'Communication under Article 94'),
                   ('new-reply', '01.01.2026', 'Response')]
        directory = '<table>' + ''.join(
            f'<tr><td>{date}</td><td><a href="?documentId={remote.replace("-", "")}">{title}</a></td></tr>'
            for remote, date, title in entries) + '</table>'

        def fetch(url):
            data = directory.encode() if 'tab=doclist' in url else b'%PDF-fixture'
            return data, url, 'text/html' if 'tab=doclist' in url else 'application/pdf'

        def downloaded(store, case_id, document, url, fetcher):
            # No network or PDF extraction: retain the orchestrator's actual metadata.
            def save(current):
                row = next(d for d in current['documents'] if d['id'] == document['id'])
                row.update(document, status='downloaded', language='en',
                           text='1. A converter.' if document['role'] == 'claims' else 'Applicant response.')
            store.update(case_id, save)
            return True

        with patch.object(self.module, '_download', side_effect=downloaded):
            self.module.research_ep(self.store, case['id'], 'EP22123456', fetch)
        current = self.store.get(case['id'])
        sources = analyze_case(current)['sources']
        self.assertEqual(sources['claims']['remote_id'], 'oldclaims')
        self.assertEqual(sources['response']['remote_id'], 'oldreply')
        latest = next(d for d in current['documents'] if d['remote_id'] == 'newreply')
        self.assertEqual(latest['status'], 'downloaded')
        self.assertNotEqual(latest.get('cycle_id'), sources['claims'].get('cycle_id'))


if __name__ == '__main__': unittest.main()
