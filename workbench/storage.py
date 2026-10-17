"""Atomic case storage; imported documents are immutable and content-addressed."""
import hashlib
import io
import json
import os
import re
import threading
import uuid
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from .claims import normalize_number
from .retrieval import MAX_BYTES, validate_pdf

ROLES = {'oa', 'response', 'claims', 'publication', 'original', 'other'}
VERSIONS = {'unknown', 'pending', 'granted', 'reference', 'publication', 'not_entered', 'auxiliary'}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def safe_name(name):
    name = str(name).replace('\\', '/').split('/')[-1]
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(' .')[:150]
    return name or 'document.txt'


def extract_text(data, suffix):
    notes = []
    if suffix in ('.txt', '.md'):
        text = data.decode('utf-8-sig')
        pages = [{'number': 1, 'text': text}]
    elif suffix == '.pdf':
        validate_pdf(data)
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise ValueError('PDF 已加密，请导入可读取的副本')
            pages = [{'number': i + 1, 'text': page.extract_text() or ''} for i, page in enumerate(reader.pages)]
        except ImportError:
            pages = []
            notes.append('未安装 PDF 文本提取组件；原件已保存，可补充 TXT 文本')
        text = '\n\n'.join(p['text'] for p in pages)
        if not text.strip():
            notes.append('扫描件或无可提取文字；尚未 OCR，请补充可检索 PDF 或 TXT')
    elif suffix == '.docx':
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(i.file_size for i in archive.infolist()) > 80 * 1024 * 1024:
                raise ValueError('Word 文档解压后过大')
            root = ET.fromstring(archive.read('word/document.xml'))
            namespace = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
            marked = any(node.tag in (namespace + 'ins', namespace + 'del') or (node.tag in (namespace + 'strike', namespace + 'dstrike', namespace + 'u') and node.attrib.get(namespace + 'val', 'true') not in ('false', '0', 'none')) for node in root.iter())
            if marked:
                notes.append('发现修订标记或下划线/删除线；提取文字不代表清洁稿，请另行补充清洁文本')
        try:
            from docx import Document
            from docx.text.paragraph import Paragraph
        except ImportError as exc:
            raise ValueError('请先安装 requirements.txt 中的 Word 组件') from exc
        doc = Document(io.BytesIO(data))

        def inner_text(container):
            parts = []
            for block in container.iter_inner_content():
                if isinstance(block, Paragraph):
                    parts.append(block.text)
                else:
                    parts.extend(' | '.join(inner_text(cell) for cell in row.cells) for row in block.rows)
            return '\n'.join(parts)

        text = inner_text(doc)
        pages = [{'number': None, 'text': text}]
        notes.append('Word 文本位置按段落，未推测分页')
    else:
        raise ValueError('支持 PDF、DOCX、UTF-8 TXT 和 Markdown 文件')
    return text, pages, notes


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def case_dir(self, case_id):
        if not re.fullmatch(r'[a-f0-9]{16}', str(case_id)):
            raise ValueError('案件 ID 格式错误')
        return self.root / case_id

    def create(self, number, target_country='BR'):
        from .parsers import default_backend
        number = normalize_number(number)
        target_country = str(target_country).upper()
        if not re.fullmatch(r'[A-Z]{2}', target_country):
            raise ValueError('目标法域须为两位代码，例如 BR')
        case = {'id': uuid.uuid4().hex[:16], 'input_number': number, 'target_country': target_country, 'target_application': number if number[:2] == target_country else '', 'title': '', 'status': 'idle', 'family': [], 'documents': [], 'events': [], 'settings': {'source_member': 'EP', 'review_enabled': False}, 'exports': [], 'analysis': {}, 'gaps': ['尚未获取案卷；可以启动检索或补充文件'], 'created_at': now(), 'updated_at': now()}
        case['settings']['ocr_engine']=default_backend(self.root)
        with self.lock:
            self.case_dir(case['id']).mkdir()
            self._save(case)
        return case

    def _save(self, case):
        destination = self.case_dir(case['id']) / 'case.json'
        temporary = destination.with_name(uuid.uuid4().hex + '.tmp')
        temporary.write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temporary, destination)

    def get(self, case_id):
        with self.lock:
            return json.loads((self.case_dir(case_id) / 'case.json').read_text(encoding='utf-8'))

    def update(self, case_id, transform):
        with self.lock:
            case = self.get(case_id)
            transform(case)
            case['updated_at'] = now()
            self._save(case)
            return case

    def list(self):
        with self.lock:
            result = []
            for path in self.root.glob('*/case.json'):
                try:
                    case = json.loads(path.read_text(encoding='utf-8'))
                    result.append({**{k: case.get(k) for k in ('id', 'input_number', 'target_country', 'title', 'status', 'updated_at', 'is_demo', 'exports_stale')}, 'has_exports': bool(case.get('exports'))})
                except (OSError, ValueError):
                    continue
            return sorted(result, key=lambda c: c['updated_at'], reverse=True)

    def log(self, case_id, message):
        return self.update(case_id, lambda c: c['events'].append({'time': now(), 'message': str(message)[:2000]}))

    def import_document(self, case_id, data, meta):
        if not data or len(data) > MAX_BYTES:
            raise ValueError('文件为空或超过 25 MB')
        filename = safe_name(meta.get('filename', 'document.txt'))
        role = meta.get('role', 'other')
        version = meta.get('version_status', 'unknown')
        if role not in ROLES or version not in VERSIONS:
            raise ValueError('未知文件类型或版本状态')
        date = meta.get('date', '')
        if date:
            datetime.strptime(date, '%Y-%m-%d')
        country = str(meta.get('country', '')).upper()
        if country and not re.fullmatch('[A-Z]{2}', country):
            raise ValueError('文件所属法域须为两位代码')
        text, pages, notes = extract_text(data, Path(filename).suffix.lower())
        if meta.get('requires_clean_text'):
            notes.append('发现修订标记：来源目录将此文件标为带批注或修改痕迹版本；请补充清洁文本')
        requires_clean = any('发现修订标记' in note for note in notes) and role in ('claims', 'response')
        if requires_clean:
            version = 'unknown'
        digest = hashlib.sha256(data).hexdigest()
        docid = uuid.uuid4().hex[:16]
        relative = 'originals/' + docid + '-' + filename
        destination = self.case_dir(case_id) / relative
        destination.parent.mkdir(exist_ok=True)
        destination.write_bytes(data)
        doc = {'id': docid, 'title': str(meta.get('title') or filename)[:300], 'country': country, 'date': date, 'role': role, 'status': 'imported', 'url': str(meta.get('source_url') or meta.get('url') or ''), 'filename': filename, 'local_path': relative, 'text': text, 'pages': pages, 'version_status': version, 'language': meta.get('language', 'en'), 'sha256': digest, 'notes': notes, 'retrieved_at': now(), 'requires_clean_text': requires_clean}
        for key in ('application', 'publication', 'cycle_id', 'response_id', 'remote_id'):
            if meta.get(key):
                doc[key] = str(meta[key])
        def add(case):
            case['documents'].append(doc)
            case['exports_stale'] = bool(case.get('exports'))
        self.update(case_id, add)
        return doc

    def edit_document(self, case_id, docid, fields):
        permitted = {'title', 'role', 'country', 'date', 'language', 'version_status', 'application', 'publication', 'cycle_id', 'source_url'}
        if set(fields) - permitted or not all(isinstance(v, str) for v in fields.values()):
            raise ValueError('文件信息格式错误')
        if fields.get('role') and fields['role'] not in ROLES:
            raise ValueError('未知文件类型')
        if fields.get('version_status') and fields['version_status'] not in VERSIONS:
            raise ValueError('未知版本状态')
        if fields.get('date'):
            datetime.strptime(fields['date'], '%Y-%m-%d')
        if fields.get('country') and not re.fullmatch('[A-Z]{2}', fields['country']):
            raise ValueError('法域须为两位大写代码')
        def edit(case):
            doc = next((d for d in case['documents'] if d['id'] == docid), None)
            if doc is None:
                raise FileNotFoundError('文件不存在')
            doc.setdefault('metadata_history', []).append({'time': now(), 'before': {k: doc.get(k) for k in fields}})
            doc.update({('url' if k == 'source_url' else k): v for k, v in fields.items()})
            doc['requires_clean_text'] = any('发现修订标记' in str(note) for note in doc.get('notes', [])) and doc['role'] in ('claims', 'response')
            case['exports_stale'] = bool(case.get('exports'))
        return self.update(case_id, edit)

    def ocr_case(self, case_id):
        from .ocr import cache_version, recognize_pdf
        from .metadata import english_evidence, enrich_case_documents
        from .parsers import BACKENDS, default_backend
        requested = (self.get(case_id).get('settings') or {}).get('ocr_engine') or default_backend(self.root)
        if requested not in ('rapidocr', *BACKENDS):
            raise ValueError('未知英文材料解析器')
        def selected_engine(doc):
            language = str(doc.get('language') or '').lower()
            english = language in ('en', 'eng', 'english', 'en-us', 'en-gb')
            if language in ('', 'unknown', 'und'):
                english = bool(english_evidence(doc.get('text') or ''))
            return requested if english and doc.get('role') in ('oa','response','claims') else 'rapidocr'

        attempted = set()
        priority = {'oa': 0, 'response': 1, 'claims': 2, 'original': 3, 'publication': 4}
        # A fresh scan first needs language evidence. The second pass upgrades
        # newly identified English key documents without repeating failed work.
        for phase in range(2 if requested != 'rapidocr' else 1):
            documents = sorted(self.get(case_id)['documents'], key=lambda d: (priority.get(d.get('role'), 5), bool(d.get('requires_clean_text'))))
            for doc in documents:
                if not doc.get('local_path') or Path(doc['local_path']).suffix.lower() != '.pdf':
                    continue
                engine = selected_engine(doc)
                if (doc['id'], engine) in attempted:
                    continue
                attempted.add((doc['id'], engine))
                previous = doc.get('ocr') or {}
                if previous.get('version') == cache_version(engine) and previous.get('status') in ('complete', 'not_needed'):
                    continue
                path = (self.case_dir(case_id) / doc['local_path']).resolve()
                if not path.is_relative_to(self.case_dir(case_id)):
                    raise PermissionError('无效原件路径')
                self.log(case_id, '正在识别扫描材料：' + doc['title'])
                try:
                    data = path.read_bytes()
                    if hashlib.sha256(data).hexdigest() != doc['sha256']:
                        raise ValueError('原件 SHA256 不一致，未执行 OCR')
                    kwargs = {'engine':engine} if engine != 'rapidocr' else {}
                    result = recognize_pdf(data, self.root / '.ocr-cache',
                        log=lambda message: self.log(case_id, doc['title'][:65] + ' · ' + message), **kwargs)
                except Exception as exc:
                    self.log(case_id, f'OCR 未完成 {doc["title"]}：{str(exc)[:200]}；已有文字保留')
                    result = {'status': 'failed', 'engine':engine, 'version': cache_version(engine),
                              'notes': ['OCR：' + str(exc)[:250] + '；已有识别文字已保留。']}
                def apply(case):
                    current = next((d for d in case['documents'] if d['id'] == doc['id']), None)
                    if current is None:
                        return
                    preserve = (bool(str(current.get('draft_text') or current.get('text') or '').strip())
                                and result.get('status') not in ('complete', 'not_needed'))
                    if 'pages' in result and not preserve:
                        if current.get('ocr') and str(current.get('text') or '').strip():
                            snapshot = {k:current.get(k) for k in ('text','draft_text','pages','ocr','notes')}
                            encoded = json.dumps(snapshot,ensure_ascii=False,sort_keys=True).encode('utf-8')
                            relative = 'derived/' + doc['id'] + '-' + hashlib.sha256(encoded).hexdigest()[:16] + '.json'
                            archive = self.case_dir(case_id) / relative
                            archive.parent.mkdir(exist_ok=True)
                            if not archive.exists():archive.write_bytes(encoded)
                            if not any(h.get('path') == relative for h in current.setdefault('ocr_history',[])):
                                current['ocr_history'].append(dict(path=relative,version=previous.get('version'),time=now()))
                        # Full OCR geometry remains in its cache, outside API polls.
                        pages = [{**{k: v for k, v in p.items() if k not in ('lines','blocks','ocr_lines','parser_blocks','parser_ocr_text')}, 'line_count': len(p.get('lines', p.get('ocr_lines',[])))} for p in result['pages']]
                        current.update(text=result['text'], draft_text=result.get('body_text',''), pages=pages)
                    current['ocr'] = {k: v for k, v in result.items() if k not in ('pages', 'text', 'body_text', 'notes', 'engine_document','parser_ocr_text','parser_body_text')}
                    current['ocr']['processed_at'] = now()
                    if preserve:
                        current['ocr']['active_text_preserved'] = True
                        result['notes'] = list(result.get('notes', [])) + ['OCR：此次解析未完整成功，继续使用已有文字及分页。']
                    current['notes'] = [n for n in current.get('notes', []) if not n.startswith(('扫描件或无可提取文字', 'OCR：'))] + result['notes']
                    case['exports_stale'] = bool(case.get('exports'))
                self.update(case_id, apply)
        # Cached OCR skips recognition, but must still repair evidence metadata.
        changes = []
        self.update(case_id, lambda c: changes.append(enrich_case_documents(c)))
        if changes[0]:
            self.log(case_id, f'已补全 {changes[0]} 项来源元数据（正文语言推断 / 同局同日候选轮次）；保留人工指定值')
        return self.get(case_id)

    def add_discovered(self, case_id, doc):
        doc = dict(doc)
        doc.setdefault('id', uuid.uuid4().hex[:16])
        for key, value in {'text': '', 'pages': [], 'notes': [], 'language': '', 'version_status': 'unknown', 'status': 'discovered', 'filename': '', 'local_path': ''}.items():
            doc.setdefault(key, value)
        def append(case):
            old = next((d for d in case['documents'] if d.get('url') and d.get('url') == doc.get('url')), None)
            if old:
                doc['id'] = old['id']
            else:
                case['documents'].append(doc)
                case['exports_stale'] = bool(case.get('exports'))
        self.update(case_id, append)
        return doc
