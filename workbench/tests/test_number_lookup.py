"""Application identifiers must resolve to verified publication pages before ingestion."""
import json
import unittest
import uuid
from pathlib import Path
from urllib.error import HTTPError

from workbench import research
from workbench.storage import Store

ROOT = Path(__file__).resolve().parents[2]


def page(publication='BR112023019754A2', application='BR112023019754A'):
    return (f'<span itemprop="publicationNumber">{publication}</span>'
            f'<span itemprop="applicationNumber">{application}</span>'
            '<span itemprop="title">A converter</span>').encode()


def results(publications):
    return json.dumps({'results': {'cluster': [{'result': [
        {'patent': {'publication_number': number}} for number in publications
    ]}]}}).encode()


class NumberLookupTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(ROOT / 'workbench-data' / 'test-runs' / uuid.uuid4().hex)

    def run_lookup(self, number, fetch):
        case = self.store.create(number)
        research.research_case(self.store, case['id'], fetch=fetch)
        return self.store.get(case['id'])

    def test_application_404_resolves_publication_and_keeps_input(self):
        def fetch(url):
            if '/patent/BR112023019754A/en' in url:
                raise HTTPError(url, 404, 'Not Found', {}, None)
            if '/xhr/query?' in url:
                return results(['BR112023019754A2']), url, 'application/json'
            if '/patent/BR112023019754A2/en' in url:
                return page(), url, 'text/html'
            raise OSError('portal not available in fixture')

        case = self.run_lookup('BR112023019754A', fetch)
        self.assertEqual(case['input_number'], 'BR112023019754A')
        self.assertEqual([m['publication'] for m in case['family']], ['BR112023019754A2'])
        self.assertTrue(any('公开号' in e['message'] and 'BR112023019754A2' in e['message'] for e in case['events']))
        self.assertFalse(case['last_error'])

    def test_search_hit_is_verified_by_application_metadata_not_rank(self):
        def fetch(url):
            if '/patent/US18279065/en' in url:
                raise HTTPError(url, 404, 'Not Found', {}, None)
            if '/xhr/query?' in url:
                return results(['US99999999B2', 'US12500504B2']), url, 'application/json'
            if '/patent/US99999999B2/en' in url:
                return page('US99999999B2', 'US12/000,000'), url, 'text/html'
            if '/patent/US12500504B2/en' in url:
                return page('US12500504B2', 'US18/279,065'), url, 'text/html'
            raise OSError('unavailable')

        case = self.run_lookup('US18/279,065', fetch)
        self.assertEqual([m['publication'] for m in case['family']], ['US12500504B2'])

    def test_fuzzy_hit_cannot_be_imported_as_this_family(self):
        def fetch(url):
            if '/xhr/query?' in url:
                return results(['BR112023019755A2']), url, 'application/json'
            if '/patent/BR112023019755A2/' in url:
                return page('BR112023019755A2', 'BR112023019755A'), url, 'text/html'
            raise HTTPError(url, 404, 'Not Found', {}, None)

        case = self.run_lookup('BR112023019754A', fetch)
        self.assertEqual(case['family'], [])
        self.assertTrue(case['last_error'])
        self.assertTrue(any(case['last_error'] in gap for gap in case['research_gaps']))

    def test_valid_publication_does_not_need_search(self):
        calls = []
        def fetch(url):
            calls.append(url)
            return page(), url, 'text/html'

        case = self.run_lookup('BR112023019754A2', fetch)
        self.assertEqual(len(case['family']), 1)
        self.assertFalse(any('/xhr/query?' in url for url in calls))

    def test_failed_search_keeps_diagnostic_and_imported_documents(self):
        case = self.store.create('BR112023019754A')
        imported = self.store.import_document(case['id'], b'1. A converter.', {'filename': 'claims.txt', 'role': 'claims', 'country': 'BR', 'version_status': 'pending'})
        def fetch(url):
            if '/xhr/query?' in url:
                raise OSError('search network timeout')
            raise HTTPError(url, 404, 'Not Found', {}, None)

        research.research_case(self.store, case['id'], fetch=fetch)
        after = self.store.get(case['id'])
        self.assertIn('search network timeout', after['last_error'])
        self.assertEqual(after['documents'][0]['id'], imported['id'])


if __name__ == '__main__':
    unittest.main()
