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
        number = normalize_number(number)
        target_country = str(target_country).upper()
        if not re.fullmatch(r'[A-Z]{2}', target_country):
            raise ValueError('目标法域须为两位代码，例如 BR')
        case = {'id': uuid.uuid4().hex[:16], 'input_number': number, 'target_country': target_country, 'target_application': number if number[:2] == target_country else '', 'title': '', 'status': 'idle', 'family': [], 'documents': [], 'events': [], 'settings': {'source_member': 'EP', 'review_enabled': False}, 'exports': [], 'analysis': {}, 'gaps': ['尚未获取案卷；可以启动检索或补充文件'], 'created_at': now(), 'updated_at': now()}
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
