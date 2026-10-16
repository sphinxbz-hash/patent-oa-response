import json
import threading
import unittest
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen

from workbench.server import create_demo, make_server
from workbench.storage import Store

ROOT = Path(__file__).resolve().parents[2]


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(ROOT / 'workbench-data' / 'test-runs' / uuid.uuid4().hex)
        self.case = create_demo(self.store)
        self.server = make_server(self.store, 0)
        self.server.generate(self.case['id'])
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f'http://127.0.0.1:{self.server.server_port}/api/cases/{self.case["id"]}'

    def preview(self, name):
        return urlopen(self.base + '/preview/' + quote(name, safe=''))

    def test_word_preview_uses_exact_paired_html_and_preserves_redline(self):
        with self.preview('MarkedClaims.docx') as response:
            self.assertIn('text/html', response.headers['Content-Type'])
            body = response.read()
        with urlopen(self.base + '/exports/MarkedClaims.html') as original:
            self.assertEqual(body, original.read())
        self.assertIn(b'<del>', body)
        self.assertIn(b'<ins>', body)

    def test_chinese_summary_and_support_table_are_readable_html(self):
        with self.preview('中文摘要.md') as response:
            summary = response.read().decode('utf-8')
        self.assertIn('<h1>同族答复包摘要</h1>', summary)
        self.assertIn('<li>', summary)
        with self.preview('SupportTable.md') as response:
            self.assertIn(b'<table>', response.read())

    def test_csv_and_json_are_rendered_without_executing_content(self):
        case = self.store.get(self.case['id'])
        folder = self.store.case_dir(case['id']) / case['export_dir']
        (folder / 'SupportTable.csv').write_text('claim,basis\n1,"<script>alert(1)</script>"\n', encoding='utf-8')
        with self.preview('SupportTable.csv') as response:
            body = response.read().decode('utf-8')
        self.assertIn('<table>', body)
        self.assertIn('&lt;script&gt;', body)
        self.assertNotIn('<script>', body)
        with self.preview('source-record.json') as response:
            self.assertIn(b'<pre>', response.read())

    def test_markdown_raw_html_and_unsafe_links_remain_inert(self):
        case = self.store.get(self.case['id'])
        folder = self.store.case_dir(case['id']) / case['export_dir']
        (folder / '中文摘要.md').write_text('# Example\n\n<script>alert(1)</script>\n\n[click](javascript:alert(1))', encoding='utf-8')
        with self.preview('中文摘要.md') as response:
            body = response.read().decode('utf-8')
        self.assertNotIn('<script>', body)
        self.assertNotIn('href="javascript:', body)
        self.assertIn('&lt;script&gt;', body)

    def test_preview_only_reads_listed_exports(self):
        for name in ('../case.json', 'case.json', 'bundle.zip'):
            with self.subTest(name=name), self.assertRaises(HTTPError):
                self.preview(name)

    def test_missing_word_companion_is_explicit_and_download_still_works(self):
        case = self.store.get(self.case['id'])
        companion = self.store.case_dir(case['id']) / case['export_dir'] / 'Response.html'
        companion.rename(companion.with_suffix('.saved'))
        with self.assertRaises(HTTPError) as error:
            self.preview('Response.docx')
        self.assertIn('重新生成', json.loads(error.exception.read())['error'])
        with urlopen(self.base + '/exports/Response.docx') as response:
            self.assertTrue(response.read().startswith(b'PK'))
