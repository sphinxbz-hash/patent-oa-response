"""Tests for the EP Register whole-dossier ZIP adapter (workbench/ep_zip.py).

Member-name fixtures reproduce the naming shapes observed in a real Register
download for application EP21934362 (dossier ZIP + toc.xml), e.g.:
  21934362-2024-11-21-1503SS-Supplementary European search report.pdf
  21934362-2025-05-09-CLMS-HWA-Amended claims with annotations.pdf
  21934362-2023-10-02-RECEIPT-OLF-(Electronic) Receipt.pdf
"""
import io
import importlib
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter

from workbench.storage import Store

ROOT = Path(__file__).resolve().parents[2]

REAL_MEMBER_NAMES = [
    '21934362-2024-11-21-1503SS-Supplementary European search report.pdf',
    '21934362-2024-11-21-1703-European search opinion.pdf',
    '21934362-2025-05-09-ABEX-Amendments received before examination.pdf',
    '21934362-2025-05-09-CLMS-HWA-Amended claims with annotations.pdf',
    '21934362-2025-05-09-CLMSABEX-Amended claims filed after receipt of (European) search report.pdf',
    '21934362-2025-03-10-1038-Letter accompanying subsequently filed items-2.pdf',
    '21934362-2023-10-02-RECEIPT-OLF-(Electronic) Receipt.pdf',
    '21934362-2023-08-11-1201-1-Information on entry into European phase.pdf',
    '21934362-2026-01-15-2035-4-Intention to grant (signatures).pdf',
    '21934362-2026-02-01-2906I-Annex to the communication.pdf',
    '21934362-2025-06-20-1226CC-Communication regarding possible amendment of the application_payment of claims fee.pdf',
]


def blank_pdf():
    buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(buffer)
    return buffer.getvalue()


class ParseMemberNameTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module('workbench.ep_zip')

    def test_real_register_shapes(self):
        expected = [
            (REAL_MEMBER_NAMES[0], '2024-11-21', ['1503SS'], 'Supplementary European search report'),
            (REAL_MEMBER_NAMES[2], '2025-05-09', ['ABEX'], 'Amendments received before examination'),
            (REAL_MEMBER_NAMES[3], '2025-05-09', ['CLMS', 'HWA'], 'Amended claims with annotations'),
            (REAL_MEMBER_NAMES[4], '2025-05-09', ['CLMSABEX'], 'Amended claims filed after receipt of (European) search report'),
            (REAL_MEMBER_NAMES[5], '2025-03-10', ['1038'], 'Letter accompanying subsequently filed items-2'),
            (REAL_MEMBER_NAMES[6], '2023-10-02', ['RECEIPT', 'OLF'], '(Electronic) Receipt'),
            (REAL_MEMBER_NAMES[7], '2023-08-11', ['1201', '1'], 'Information on entry into European phase'),
            (REAL_MEMBER_NAMES[8], '2026-01-15', ['2035', '4'], 'Intention to grant (signatures)'),
            (REAL_MEMBER_NAMES[10], '2025-06-20', ['1226CC'], 'Communication regarding possible amendment of the application_payment of claims fee'),
        ]
        for name, date, codes, title in expected:
            with self.subTest(name=name):
                parsed = self.module.parse_member_name(name)
                self.assertIsNotNone(parsed)
                self.assertEqual(parsed['date'], date)
                self.assertEqual(parsed['codes'], codes)
                self.assertEqual(parsed['title'], title)

    def test_every_real_name_parses(self):
        for name in REAL_MEMBER_NAMES:
            with self.subTest(name=name):
                self.assertIsNotNone(self.module.parse_member_name(name))

    def test_rejects_non_members(self):
        self.assertIsNone(self.module.parse_member_name('toc.xml'))
        self.assertIsNone(self.module.parse_member_name('random.pdf'))
        self.assertIsNone(self.module.parse_member_name('21934362-2024-11-21-1503SS.pdf'))  # no title

    def test_role_hints_from_document_codes(self):
        from workbench.retrieval import classify_document
        role = self.module.role_for_member
        self.assertEqual(role(['1503SS'], 'anything', classify_document), 'oa')
        self.assertEqual(role(['1703'], 'anything', classify_document), 'oa')
        self.assertEqual(role(['ABEX'], 'anything', classify_document), 'response')
        self.assertEqual(role(['CLMS', 'HWA'], 'anything', classify_document), 'claims')
        self.assertEqual(role(['CLMSABEX'], 'anything', classify_document), 'claims')
        self.assertEqual(role(['XYZ9'], 'Reply to examination report', classify_document), 'response')


class ValidateZipTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module('workbench.ep_zip')
        self.dir = ROOT / 'workbench-data' / 'test-runs' / uuid.uuid4().hex
        self.dir.mkdir(parents=True)

    def test_rejects_html_saved_as_zip(self):
        path = self.dir / 'challenge.zip'
        path.write_bytes(b'<html><title>Just a moment...</title></html>')
        with self.assertRaises(self.module.EpZipError):
            self.module.validate_zip(path)

    def test_rejects_zip_without_pdf(self):
        path = self.dir / 'empty.zip'
        with zipfile.ZipFile(path, 'w') as zf:
            zf.writestr('toc.xml', '<toc/>')
        with self.assertRaises(self.module.EpZipError):
            self.module.validate_zip(path)

    def test_accepts_zip_with_pdf(self):
        path = self.dir / 'ok.zip'
        with zipfile.ZipFile(path, 'w') as zf:
            zf.writestr(REAL_MEMBER_NAMES[0], blank_pdf())
        self.module.validate_zip(path)


class MatchMembersTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module('workbench.ep_zip')

    def test_real_dump_matches_doclist_rows(self):
        # Doclist rows as parse_ep_directory would emit them (ISO date + Register title).
        rows = []
        for index, name in enumerate(REAL_MEMBER_NAMES):
            parsed = self.module.parse_member_name(name)
            title = parsed['title'].replace('_', '/')  # Register shows a slash where ZIP uses '_'
            rows.append({'id': f'doc{index}', 'date': parsed['date'], 'title': title})
        matched = self.module.match_members(REAL_MEMBER_NAMES + ['toc.xml'], rows)
        self.assertEqual(len(matched), len(REAL_MEMBER_NAMES))
        for row in rows:
            self.assertIn(row['id'], matched)

    def test_truncated_doclist_title_still_matches(self):
        rows = [{'id': 'a', 'date': '2025-06-20',
                 'title': 'Communication regarding possible amendment of the application/payment of'}]
        matched = self.module.match_members([REAL_MEMBER_NAMES[10]], rows)
        self.assertEqual(matched, {'a': REAL_MEMBER_NAMES[10]})

    def test_wrong_date_never_matches(self):
        rows = [{'id': 'a', 'date': '1999-01-01', 'title': 'European search opinion'}]
        self.assertEqual(self.module.match_members(REAL_MEMBER_NAMES, rows), {})


class ResearchEpZipIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.research = importlib.import_module('workbench.research')
        self.ep_zip = importlib.import_module('workbench.ep_zip')
        self.store = Store(ROOT / 'workbench-data' / 'test-runs' / uuid.uuid4().hex)

    def _doclist(self, entries):
        return '<table>' + ''.join(
            f'<tr><td>{date}</td><td><a href="?documentId={docid}">{title}</a></td></tr>'
            for docid, date, title in entries) + '</table>'

    def _zip_with(self, path, names):
        with zipfile.ZipFile(path, 'w') as zf:
            for name in names:
                zf.writestr(name, blank_pdf())
            zf.writestr('toc.xml', '<toc/>')

    def test_direct_fetch_success_never_touches_browser(self):
        case = self.store.create('BR112023019754A2')
        directory = self._doclist([('OA1', '21.11.2024', 'European search opinion')])
        fetch = lambda url: (directory.encode(), url, 'text/html')
        with patch.object(self.ep_zip, 'available', return_value=True), \
             patch.object(self.ep_zip, 'fetch_ep_dossier_via_browser',
                          side_effect=AssertionError('browser must stay closed on the fast path')), \
             patch.object(self.research, '_download', return_value=True):
            self.research.research_ep(self.store, case['id'], 'EP21934362', fetch)
        current = self.store.get(case['id'])
        self.assertEqual(len(current['documents']), 1)
        self.assertEqual(current['documents'][0]['title'], 'European search opinion')

    def test_blocked_direct_fetch_falls_back_to_browser_zip(self):
        case = self.store.create('BR112023019754A2')
        entries = [
            ('ESR1', '21.11.2024', 'Supplementary European search report'),
            ('ESOP1', '21.11.2024', 'European search opinion'),
            ('CLMS1', '09.05.2025', 'Amended claims with annotations'),
            ('RCPT1', '02.10.2023', '(Electronic) Receipt'),
        ]
        directory = self._doclist(entries)
        members = [
            REAL_MEMBER_NAMES[0],   # 1503SS supplementary search report
            REAL_MEMBER_NAMES[1],   # 1703 search opinion
            REAL_MEMBER_NAMES[3],   # CLMS-HWA claims
            REAL_MEMBER_NAMES[6],   # RECEIPT-OLF receipt
            '21934362-2020-01-01-9999-Untracked paper without row.pdf',
        ]
        zip_path = self.store.case_dir(case['id']) / 'downloads' / 'EP21934362-dossier.zip'
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        self._zip_with(zip_path, members)

        def blocked(url):
            raise OSError('HTTP 403 Just a moment')

        with patch.object(self.ep_zip, 'available', return_value=True), \
             patch.object(self.ep_zip, 'fetch_ep_dossier_via_browser',
                          return_value={'html': directory, 'zip': zip_path}) as browser:
            self.research.research_ep(self.store, case['id'], 'EP21934362', blocked)
        browser.assert_called_once()
        current = self.store.get(case['id'])
        by_title = {d['title']: d for d in current['documents']}
        self.assertEqual(by_title['European search opinion']['status'], 'downloaded')
        self.assertEqual(by_title['Amended claims with annotations']['status'], 'downloaded')
        self.assertEqual(by_title['(Electronic) Receipt']['status'], 'downloaded')
        # Title classification cannot tell a search report is examiner output;
        # the 1503SS code hint upgrades the imported role.
        self.assertEqual(by_title['Supplementary European search report']['role'], 'oa')
        self.assertTrue(all(d.get('local_path') for d in by_title.values()))
        self.assertTrue(any('未能对应目录条目' in e['message'] for e in current['events']))

    def test_browser_failure_keeps_manual_guidance_path(self):
        case = self.store.create('BR112023019754A2')

        def blocked(url):
            raise OSError('HTTP 403 Just a moment')

        with patch.object(self.ep_zip, 'available', return_value=True), \
             patch.object(self.ep_zip, 'fetch_ep_dossier_via_browser',
                          side_effect=self.ep_zip.EpZipError('人机验证未通过')):
            self.research.research_ep(self.store, case['id'], 'EP21934362', blocked)
        current = self.store.get(case['id'])
        self.assertTrue(any('浏览器整包下载未成功' in e['message'] for e in current['events']))
        self.assertTrue(any('暂不可访问' in e['message'] for e in current['events']))


if __name__ == '__main__':
    unittest.main()
