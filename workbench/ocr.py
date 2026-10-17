"""Local page-level OCR. Original PDFs stay immutable; results are derived evidence."""
import hashlib
import importlib.util
import io
import json
import math
import threading
import uuid
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

MAX_PAGES = 500
DPI = 200
MAX_PIXELS = 12_000_000
_LOCK = threading.Lock()  # PDFium and the shared inference session are serialized.
_ENGINE = None


def available():
    return all(importlib.util.find_spec(name) is not None for name in ('rapidocr', 'onnxruntime', 'pypdfium2'))


def cache_version():
    try:
        engine = version('rapidocr')
        renderer = version('pypdfium2')
    except PackageNotFoundError:
        engine, renderer = 'missing', 'missing'
    return f'v1-rapidocr-{engine}-pdfium-{renderer}-{DPI}dpi'


def native_usable(text):
    text = str(text or '')
    return (sum(c.isalnum() for c in text) >= 40 and
            text.count('\ufffd') < max(2, len(text) // 50) and '(cid:' not in text)


def _recognize_page(data, index):
    import pypdfium2 as pdfium
    from rapidocr import RapidOCR

    global _ENGINE
    with _LOCK:
        if _ENGINE is None:
            _ENGINE = RapidOCR(params={'EngineConfig.onnxruntime.intra_op_num_threads': 2,
                                      'EngineConfig.onnxruntime.inter_op_num_threads': 1,
                                      'Global.log_level': 'warning'})
        pdf = pdfium.PdfDocument(data)
        try:
            page = pdf[index]
            try:
                width, height = page.get_size()
                scale = min(DPI / 72, math.sqrt(MAX_PIXELS / max(1, width * height)))
                bitmap = page.render(scale=scale)
                try:
                    image = bitmap.to_pil().convert('RGB')
                    try:
                        output = _ENGINE(image)
                        lines = [{'text': str(text), 'confidence': float(score), 'box': box.tolist()}
                                 for text, score, box in zip(output.txts or (), output.scores or (), output.boxes if output.boxes is not None else ())]
                        return {'text': '\n'.join(line['text'] for line in lines), 'lines': lines,
                                'confidence': sum(line['confidence'] for line in lines) / len(lines) if lines else 0,
                                'image_size': list(image.size), 'box_unit': 'image_pixels_top_left',
                                'page_size_points': [width, height]}
                    finally:
                        image.close()
                finally:
                    bitmap.close()
            finally:
                page.close()
        finally:
            pdf.close()


def recognize_pdf(data, cache_dir, log=lambda message: None):
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise ValueError('PDF 已加密，请提供可读取的副本')
    if len(reader.pages) > MAX_PAGES:
        raise ValueError(f'OCR 单文件上限 {MAX_PAGES} 页，请分件处理')
    digest = hashlib.sha256(data).hexdigest()
    folder = Path(cache_dir) / cache_version() / digest
    pages, notes = [], []
    engine_available = available()
    for index, page in enumerate(reader.pages):
        try:
            native = page.extract_text() or ''
        except Exception:
            native = ''
        record = {'number': index + 1, 'text': native, 'native_text': native, 'method': 'native', 'cached': False}
        if not native_usable(native):
            if not engine_available:
                record.update(method='unavailable', quality='review')
            else:
                cache = folder / f'{index + 1}.json'
                try:
                    cached = json.loads(cache.read_text(encoding='utf-8'))
                    if (not isinstance(cached.get('text'), str) or cached.get('method') != 'ocr' or
                            cached.get('number') != index + 1 or not isinstance(cached.get('lines'), list)):
                        raise ValueError('Invalid OCR cache')
                    record.update(cached, cached=True)
                except (OSError, ValueError, TypeError, AttributeError):
                    try:
                        output = _recognize_page(data, index)
                        quality = ('no_text' if not output['text'].strip() else
                                   'review' if output['confidence'] < 0.85 or any(line['confidence'] < 0.85 for line in output['lines']) else 'ok')
                        record.update(output, method='ocr', quality=quality)
                        folder.mkdir(parents=True, exist_ok=True)
                        temporary = cache.with_suffix('.' + uuid.uuid4().hex + '.tmp')
                        temporary.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
                        temporary.replace(cache)
                    except Exception as exc:
                        record.update(method='failed', quality='review', error=str(exc)[:250])
        pages.append(record)
        log(f'第 {index + 1}/{len(reader.pages)} 页：' +
            {'native': '直接提取', 'ocr': '读取缓存' if record['cached'] else 'OCR 完成', 'failed': '识别失败，可重试', 'unavailable': '未安装 OCR 组件'}[record['method']])
    failed = [p['number'] for p in pages if p['method'] == 'failed']
    low = [p['number'] for p in pages if p.get('quality') == 'review' and p['method'] == 'ocr']
    empty = [p['number'] for p in pages if p.get('quality') == 'no_text']
    missing = any(p['method'] == 'unavailable' for p in pages)
    if missing:
        notes.append('OCR：未安装本地识别组件；请安装 workbench/requirements-ocr.txt 后重试。')
    if failed:
        notes.extend(f'OCR：第 {p["number"]} 页识别失败：{p["error"]}' for p in pages if p['method'] == 'failed')
    if low:
        notes.append('OCR：以下页面置信度较低，请对照原件核对：' + ', '.join(map(str, low)))
    if empty:
        notes.append('OCR：以下页面未识别到文字，可能为空白、图纸或难以识别：' + ', '.join(map(str, empty)))
    count = sum(p['method'] == 'ocr' for p in pages)
    if count:
        notes.append('OCR：识别文字用于检索和草案；公式、符号、编号及修改痕迹需对照原件核对。')
    status = 'unavailable' if missing else 'partial' if failed else 'complete' if count else 'not_needed'
    return {'pages': pages, 'text': '\n\n'.join(p['text'] for p in pages), 'notes': notes,
            'status': status, 'version': cache_version(), 'ocr_pages': count,
            'native_pages': sum(p['method'] == 'native' for p in pages), 'failed_pages': failed,
            'review_pages': low, 'empty_pages': empty, 'cached_pages': sum(p['cached'] for p in pages)}


def labelled_text(document):
    lines = [document.get('title', ''), '原件 SHA256：' + document.get('sha256', ''),
             '文字为提取/OCR 派生结果；请对照原 PDF 核对。', '']
    for page in document.get('pages', []):
        method = {'native': '原文提取', 'ocr': 'OCR', 'failed': '识别失败', 'unavailable': '待 OCR'}.get(page.get('method'), '原文提取')
        score = f' · 行平均置信度 {page["confidence"]:.1%}' if page.get('method') == 'ocr' else ''
        lines += [f'--- 第 {page.get("number") or "?"} 页 · {method}{score} ---', page.get('text', '').strip() or '[未取得文字]', '']
    return '\n'.join(lines)
