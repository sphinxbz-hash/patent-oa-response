import importlib
import json
import threading
import unittest
import uuid
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from workbench.storage import Store

ROOT = Path(__file__).resolve().parents[2]


class ServerTests(unittest.TestCase):
    def test_second_launch_does_not_reset_running_case_status(self):
        case = self.store.create('BR112023019754A2')
        self.store.update(case['id'], lambda c: c.update(status='researching'))
        with self.assertRaises(OSError):
            importlib.import_module('workbench.server').make_server(self.store, self.server.server_port)
        self.assertEqual(self.store.get(case['id'])['status'], 'researching')

    def setUp(self):
        self.assertTrue((ROOT / 'workbench/server.py').exists(), 'HTTP application not implemented')
        server_module = importlib.import_module('workbench.server')
        self.store = Store(ROOT / 'workbench-data' / 'test-runs' / uuid.uuid4().hex)
        self.server = server_module.make_server(self.store, port=0)
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, path, payload=None, headers=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = Request(self.base + path, data=data, headers={'Content-Type':'application/json', **(headers or {})})
        with urlopen(req) as response:
            return json.loads(response.read())

    def test_create_import_select_reload(self):
        case = self.request('/api/cases', {'application_number':'CN117691670A','target_country':'BR','auto_research':False})
        path = '/api/cases/' + case['id']
        case = self.request(path + '/documents', {'filename':'claims.txt','text':'1. A converter.','role':'claims','country':'BR','version_status':'pending','language':'en'})
        doc_id = case['documents'][0]['id']
        case = self.request(path + '/settings', {'pending_claims_id':doc_id,'review_enabled':False})
        self.assertEqual(case['settings']['pending_claims_id'], doc_id)
        self.assertEqual(self.request(path)['documents'][0]['text'], '1. A converter.')
        case = self.request(path + '/documents/' + doc_id, {'date':'2026-10-01','language':'en','application':'BR112023019754'})
        self.assertEqual(case['documents'][0]['date'], '2026-10-01')
        with urlopen(self.base + path + '/files/' + doc_id) as response:
            self.assertEqual(response.read(), b'1. A converter.')

    def test_cross_origin_write_rejected(self):
        with self.assertRaises(HTTPError) as error:
            self.request('/api/cases', {'application_number':'CN117691670A','auto_research':False}, {'Origin':'https://evil.example'})
        self.assertEqual(error.exception.code, 403)

    def test_path_and_invalid_settings_rejected(self):
        case = self.request('/api/cases', {'application_number':'CN117691670A','auto_research':False})
        with self.assertRaises(HTTPError) as error:
            self.request('/api/cases/' + case['id'] + '/settings', {'pending_claims_id':'does-not-exist'})
        self.assertEqual(error.exception.code, 400)
        with self.assertRaises(HTTPError):
            self.request('/api/cases/' + case['id'] + '/exports/..%2Fcase.json')


if __name__ == '__main__': unittest.main()
