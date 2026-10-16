"""Local HTTP interface. Case files never leave this machine on import/export."""
import base64
import binascii
import hashlib
import json
import mimetypes
import os
import re
import threading
import traceback
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote, quote

from .storage import MAX_BYTES, Store
from .research import research_case
from . import __version__

STATIC = Path(__file__).parent / 'static'
SETTING_KEYS = {'source_member', 'selected_response_id', 'selected_claims_id', 'pending_claims_id', 'target_oa_id', 'original_id', 'review_enabled', 'response_override', 'claims_override', 'support_rows', 'deadline'}


def instance_info(data_dir):
    identity = os.path.normcase(str(Path(data_dir).resolve()))
    return {'service': 'patent-oa-response-workbench', 'version': __version__,
            'data_root': hashlib.sha256(identity.encode('utf-8')).hexdigest()}


class WorkbenchHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = os.name != 'nt'

    def __init__(self, address, store):
        super().__init__(address, Handler)
        self.store = store
        self.jobs = {}
        self.job_lock = threading.Lock()
        self.capacity = threading.BoundedSemaphore(2)

    def start_job(self, case_id, operation):
        with self.job_lock:
            if case_id in self.jobs:
                raise RuntimeError('该案件已有任务正在运行，请等待完成')
            if len(self.jobs) >= 6:
                raise RuntimeError('已有多个案件正在处理，请稍后再试')
            self.store.update(case_id, lambda c: c.update(status='researching' if operation == 'research' else 'generating', last_error=''))
            def work():
                try:
                    with self.capacity:
                        if operation == 'research':
                            research_case(self.store, case_id)
                        else:
                            self.generate(case_id)
                except Exception as exc:
                    self.store.update(case_id, lambda c: c.update(status='idle', last_error=str(exc)))
                    self.store.log(case_id, '任务未完成：' + str(exc)[:250])
                    traceback.print_exc()
                finally:
                    with self.job_lock:
                        self.jobs.pop(case_id, None)
            thread = threading.Thread(target=work, daemon=True)
            self.jobs[case_id] = thread
            thread.start()

    def generate(self, case_id):
        from .drafting import generate_package
        case = self.store.get(case_id)
        self.store.log(case_id, '正在整理证据和生成英文答复包')
        directory = 'exports/' + uuid.uuid4().hex[:12]
        folder = self.store.case_dir(case_id) / directory
        folder.mkdir(parents=True)
        result = generate_package(case, folder)
        exports = result['exports']
        for entry in exports:
            entry['url'] = f"/api/cases/{case_id}/exports/{quote(entry['name'])}"
        bundles = list(folder.glob('*.zip'))
        bundle = bundles[0] if bundles else folder / 'bundle.zip'
        if not bundles:
            with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as archive:
                for path in folder.iterdir():
                    if path.is_file() and path.suffix != '.zip':
                        archive.write(path, path.name)
        with zipfile.ZipFile(bundle, 'a', zipfile.ZIP_DEFLATED) as archive:
            for document in case['documents']:
                if document.get('local_path'):
                    path = (self.store.case_dir(case_id) / document['local_path']).resolve()
                    if path.is_relative_to(self.store.case_dir(case_id)) and path.is_file():
                        archive.write(path, 'originals/' + path.name)
        self.store.update(case_id, lambda c: c.update(status='idle', exports=exports, exports_stale=False, export_dir=directory, bundle_name=bundle.name, analysis=result['analysis'], gaps=result['gaps'], last_error=''))
        self.store.log(case_id, f'答复包已生成：{len(exports)} 个可打开文件；缺口已列入中文摘要')


class Handler(BaseHTTPRequestHandler):
    server_version = 'PatentWorkbench/0.1'

    def log_message(self, fmt, *args):
        pass

    def _guard(self, mutation=False):
        host = self.headers.get('Host', '')
        allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        if host not in allowed:
            raise PermissionError('仅允许本机访问')
        origin = self.headers.get('Origin')
        if origin and origin not in {'http://' + h for h in allowed}:
            raise PermissionError('拒绝来自其他网站的请求')
        if mutation and self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            raise ValueError('请求必须为 application/json')

    def _send(self, body, content_type='application/json; charset=utf-8', status=200, filename=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'self'")
        if filename:
            mode = 'inline' if content_type.startswith(('text/', 'application/pdf')) else 'attachment'
            self.send_header('Content-Disposition', f"{mode}; filename*=UTF-8''{quote(filename)}")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, value, status=200):
        self._send(json.dumps(value, ensure_ascii=False).encode('utf-8'), status=status)

    def _case(self, case_id):
        case = self.server.store.get(case_id)
        # Original file text is intentionally available for local inspection; paths remain relative.
        for doc in case['documents']:
            if doc.get('local_path'):
                doc['file_url'] = f"/api/cases/{case_id}/files/{doc['id']}"
        return case

    def _file(self, path, name=None):
        if not path.is_file():
            raise FileNotFoundError('文件尚未生成或不存在')
        content_type = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        if path.suffix in ('.md', '.txt', '.csv'):
            content_type = 'text/plain; charset=utf-8'
        self._send(path.read_bytes(), content_type, filename=name or path.name)

    def do_GET(self):
        try:
            self._guard()
            path = unquote(urlparse(self.path).path)
            if path == '/api/health':
                return self._json(instance_info(self.server.store.root))
            if path == '/api/cases':
                return self._json({'cases': self.server.store.list()})
            match = re.fullmatch(r'/api/cases/([a-f0-9]{16})(?:/(.*))?', path)
            if match:
                case_id, tail = match.groups()
                case = self._case(case_id)
                if not tail:
                    return self._json(case)
                if tail.startswith('preview/'):
                    from .preview import render_export
                    allowed = {entry['name'] for entry in case.get('exports', [])}
                    folder = (self.server.store.case_dir(case_id) / case.get('export_dir', 'exports')).resolve()
                    if not folder.is_relative_to(self.server.store.case_dir(case_id)):
                        raise PermissionError('无效交付目录')
                    return self._send(render_export(folder, tail[8:], allowed), 'text/html; charset=utf-8')
                if tail == 'reports/00-family-history.md':
                    from .analysis import analyze_case
                    from .drafting import _write_history
                    folder = self.server.store.case_dir(case_id) / 'reports'
                    folder.mkdir(exist_ok=True)
                    _write_history(case, analyze_case(case), folder)
                    return self._file(folder / '00-family-history.md')
                if tail.startswith('files/'):
                    docid = tail[6:]
                    doc = next((d for d in case['documents'] if d['id'] == docid), None)
                    if not doc or not doc.get('local_path'):
                        raise FileNotFoundError('原件尚未下载')
                    file = (self.server.store.case_dir(case_id) / doc['local_path']).resolve()
                    if not file.is_relative_to(self.server.store.case_dir(case_id)):
                        raise PermissionError('无效文件路径')
                    return self._file(file, doc.get('filename'))
                if tail == 'bundle' or tail.startswith('exports/'):
                    filename = case.get('bundle_name', '') if tail == 'bundle' else tail[8:]
                    allowed = {e['name'] for e in case.get('exports', [])} | {case.get('bundle_name', '')}
                    if not filename or filename not in allowed or Path(filename).name != filename or '/' in filename or '\\' in filename:
                        raise FileNotFoundError('找不到交付文件')
                    return self._file(self.server.store.case_dir(case_id) / case.get('export_dir', 'exports') / filename)
                raise FileNotFoundError('接口不存在')
            if path in ('/', '/index.html'):
                return self._file(STATIC / 'index.html')
            if path in ('/static/app.js', '/static/style.css'):
                return self._file(STATIC / path.rsplit('/', 1)[-1])
            raise FileNotFoundError('页面不存在')
        except Exception as exc:
            self._error(exc)

    def _error(self, exc):
        status = 403 if isinstance(exc, PermissionError) else 404 if isinstance(exc, FileNotFoundError) else 409 if isinstance(exc, RuntimeError) else 400 if isinstance(exc, (ValueError, KeyError, binascii.Error, UnicodeError)) else 500
        self._json({'error': str(exc) if status != 500 else '处理失败，请查看案件事件或服务日志'}, status)

    def do_POST(self):
        try:
            self._guard(True)
            size = int(self.headers.get('Content-Length', '0'))
            if size <= 0 or size > MAX_BYTES * 4 // 3 + 100000:
                raise ValueError('请求为空或超过上传限制')
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('请求应为对象')
            path = urlparse(self.path).path
            if path == '/api/cases':
                case = self.server.store.create(data.get('application_number', ''), data.get('target_country', 'BR'))
                if data.get('auto_research', True):
                    self.server.start_job(case['id'], 'research')
                return self._json(self._case(case['id']), 201)
            if path == '/api/demo':
                case = create_demo(self.server.store)
                self.server.start_job(case['id'], 'generate')
                return self._json(self._case(case['id']), 201)
            match = re.fullmatch(r'/api/cases/([a-f0-9]{16})/(settings|documents|research|generate)(?:/([a-f0-9]{16}))?', path)
            if not match:
                raise FileNotFoundError('接口不存在')
            case_id, action, document_id = match.groups()
            case = self._case(case_id)
            if action in ('research', 'generate'):
                self.server.start_job(case_id, action)
            else:
                with self.server.store.lock:
                    case = self._case(case_id)
                    if case['status'] == 'generating':
                        raise RuntimeError('正在生成文件，请完成后再修改材料')
                    if document_id:
                        if action != 'documents':
                            raise FileNotFoundError('接口不存在')
                        source = data.get('source_url', '')
                        if source and urlparse(source).scheme not in ('http', 'https'):
                            raise ValueError('来源地址须为 http 或 https 链接')
                        self.server.store.edit_document(case_id, document_id, data)
                    elif action == 'settings':
                        self._settings(case_id, case, data)
                    else:
                        source = str(data.get('source_url') or '')
                        if source and (urlparse(source).scheme not in ('http', 'https') or not urlparse(source).hostname):
                            raise ValueError('来源地址须为 http 或 https 链接')
                        content = str(data['text']).encode('utf-8') if 'text' in data else base64.b64decode(data.get('data_base64', ''), validate=True)
                        self.server.store.import_document(case_id, content, data)
                        self.server.store.log(case_id, f"已补充文件 {data.get('filename', 'document.txt')}")
            return self._json(self._case(case_id))
        except Exception as exc:
            self._error(exc)

    def _settings(self, case_id, case, data):
        if set(data) - SETTING_KEYS - {'target_application'}:
            raise ValueError('包含不支持的设置字段')
        ids = {d['id'] for d in case['documents']}
        for key, value in data.items():
            if key.endswith('_id') and value and value not in ids:
                raise ValueError('所选文件不存在')
        for key in ('response_override', 'claims_override'):
            if key in data and (not isinstance(data[key], str) or len(data[key]) > 2_000_000):
                raise ValueError('文本内容类型错误或过长')
        if 'review_enabled' in data and not isinstance(data['review_enabled'], bool):
            raise ValueError('review_enabled 应为布尔值')
        if 'support_rows' in data and (not isinstance(data['support_rows'], list) or not all(isinstance(row, dict) for row in data['support_rows'])):
            raise ValueError('修改依据应为行对象数组')
        if 'deadline' in data and not isinstance(data['deadline'], dict):
            raise ValueError('期限设置格式错误')
        if 'source_member' in data and not isinstance(data['source_member'], str):
            raise ValueError('参考同族格式错误')
        def save(c):
            c['settings'].update({k: v for k, v in data.items() if k in SETTING_KEYS})
            if 'target_application' in data:
                c['target_application'] = str(data['target_application'])[:80]
            if c.get('exports'):
                c['exports_stale'] = True
        self.server.store.update(case_id, save)


def create_demo(store):
    case = store.create('CN000000001A', 'BR')
    store.update(case['id'], lambda c: c.update(is_demo=True, title='演示案件（虚构数据）', target_application='BR000000001', family=[{'country':'EP','publication':'EP0000001B1','application':'EP00000001','status':'演示授权状态，非真实案件','status_source':'虚构演示数据','url':''}]))
    common = {'language':'en', 'date':'2026-01-10'}
    rows = [
        ('original.txt', 'original', 'BR', 'reference', 'Original application\nParagraph 12. A converter comprises a bridge and a controller. The controller measures input current and selects one of four operating modes. Each operating cycle spans a complete switching period.'),
        ('target-oa.txt', 'oa', 'BR', 'unknown', 'Office Action\nInventive step\nClaim 1 is considered to lack inventive step in view of EP0000002A1. The distinction between continuous and intermittent operation should be clarified.'),
        ('pending-claims.txt', 'claims', 'BR', 'pending', '1. A converter comprising a bridge and a controller.\n2. The converter of claim 1, wherein the controller measures input current.'),
        ('family-response.txt', 'response', 'EP', 'reference', 'Response for EP00000001\nInventive step\nEP0000002A1 describes continuous operation. Amended claim 1 requires selecting one of four operating modes based on the input current, including an intermittent mode. The cited passage does not describe this selection.\nAmendments\nThe input-current measurement limitation previously recited in claim 2 has been incorporated into claim 1.'),
        ('family-claims.txt', 'claims', 'EP', 'granted', '1. A converter comprising a bridge and a controller, wherein the controller measures input current and selects one of four operating modes including an intermittent mode.\n2. The converter of claim 1, wherein each operating cycle spans a complete switching period.')]
    docs = {}
    for filename, role, country, version, text in rows:
        text = 'FICTIONAL DEMONSTRATION ONLY. Not a real patent case.\n\n' + text
        doc = store.import_document(case['id'], text.encode('utf-8'), dict(common, filename=filename, title=filename + ' (fictional demo)', role=role, country=country, version_status=version, application='EP00000001' if country == 'EP' else 'BR000000001', cycle_id='demo-cycle'))
        docs[filename] = doc
    settings = {'source_member':'EP', 'review_enabled':False, 'selected_response_id':docs['family-response.txt']['id'], 'selected_claims_id':docs['family-claims.txt']['id'], 'pending_claims_id':docs['pending-claims.txt']['id'], 'target_oa_id':docs['target-oa.txt']['id'], 'original_id':docs['original.txt']['id'], 'support_rows':[{'claim':'1','change':'Input current and four operating modes','basis':'The controller measures input current and selects one of four operating modes.','source_id':docs['original.txt']['id'],'page':1}]}
    return store.update(case['id'], lambda c: c.update(settings=settings, gaps=['虚构演示案件，仅用于体验流程']))


def make_server(store, port=8765):
    server = WorkbenchHTTPServer(('127.0.0.1', port), store)
    for case in store.list():
        if case['status'] in ('researching', 'generating'):
            store.update(case['id'], lambda c: c.update(status='idle', last_error='上次服务中断；可重新检索或生成'))
    return server
