import contextlib
import io
import json
import threading
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from workbench.__main__ import main
from workbench.server import make_server
from workbench.storage import Store

ROOT = Path(__file__).resolve().parents[2]


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(ROOT / 'workbench-data' / 'test-runs' / uuid.uuid4().hex)
        self.server = make_server(self.store, 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def invoke(self, data_dir):
        args = ['workbench', '--port', str(self.server.server_port), '--data-dir', str(data_dir), '--open']
        with patch('sys.argv', args), patch('webbrowser.open') as browser, contextlib.redirect_stdout(io.StringIO()):
            main()
            return browser

    def test_repeated_launch_opens_existing_instance_without_mutating_cases(self):
        case = self.store.create('BR112023019754A2')
        self.store.update(case['id'], lambda c: c.update(status='researching'))
        browser = self.invoke(self.store.root)
        browser.assert_called_once_with(self.url)
        self.assertEqual(self.store.get(case['id'])['status'], 'researching')

    def test_health_identifies_instance_without_returning_case_data(self):
        with urlopen(self.url + '/api/health') as response:
            body = json.loads(response.read())
        self.assertEqual(body['service'], 'patent-oa-response-workbench')
        self.assertTrue(body['data_root'])
        self.assertNotIn('cases', body)

    def test_other_data_directory_is_not_opened(self):
        with patch('webbrowser.open') as browser, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                self.invoke(self.store.root / 'another')
        self.assertNotEqual(error.exception.code, 0)
        browser.assert_not_called()

    def test_unrelated_server_is_not_opened(self):
        class Unrelated(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"service":"another-app"}')
        unrelated = ThreadingHTTPServer(('127.0.0.1', 0), Unrelated)
        threading.Thread(target=unrelated.serve_forever, daemon=True).start()
        self.addCleanup(unrelated.server_close)
        self.addCleanup(unrelated.shutdown)
        with patch('sys.argv', ['workbench', '--port', str(unrelated.server_port), '--data-dir', str(self.store.root), '--open']), patch('webbrowser.open') as browser, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                main()
        self.assertNotEqual(error.exception.code, 0)
        browser.assert_not_called()
