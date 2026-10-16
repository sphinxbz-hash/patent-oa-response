"""Read existing exports as inert HTML; never regenerate or alter the draft."""
import csv
import html
import io
import json
import re
from pathlib import Path

MAX_PREVIEW_BYTES = 8 * 1024 * 1024


def _table(rows):
    if not rows:
        return '<p>表格没有内容。</p>'
    head, *body = rows
    return ('<div class="table-wrap"><table><thead><tr>' +
            ''.join('<th>' + html.escape(cell) + '</th>' for cell in head) +
            '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + html.escape(cell) + '</td>' for cell in row) + '</tr>' for row in body) +
            '</tbody></table></div>')


def _cells(line):
    return [cell.strip().replace(r'\|', '|') for cell in re.split(r'(?<!\\)\|', line.strip().strip('|'))]


def _markdown(source):
    """The generated reports need headings, tables, lists and quoted evidence.

    HTML and inline link syntax remain text. No arbitrary source HTML executes.
    """
    lines, result, index = source.splitlines(), [], 0
    while index < len(lines):
        line = lines[index].strip()
        index += 1
        if not line:
            continue
        if line.startswith('```'):
            code = []
            while index < len(lines) and not lines[index].strip().startswith('```'):
                code.append(lines[index]); index += 1
            index += 1
            result.append('<pre>' + html.escape('\n'.join(code)) + '</pre>')
        elif '|' in line and index < len(lines) and re.fullmatch(r'\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?', lines[index].strip()):
            rows = [_cells(line)]
            index += 1
            while index < len(lines) and '|' in lines[index] and lines[index].strip():
                rows.append(_cells(lines[index])); index += 1
            result.append(_table(rows))
        elif heading := re.match(r'^(#{1,6})\s+(.+)$', line):
            level = len(heading.group(1))
            result.append(f'<h{level}>' + html.escape(heading.group(2)) + f'</h{level}>')
        elif line.startswith(('- ', '* ')) or re.match(r'^\d+\.\s', line):
            ordered = bool(re.match(r'^\d+\.\s', line))
            pattern = r'^\d+\.\s+' if ordered else r'^[-*]\s+'
            items = [re.sub(pattern, '', line)]
            while index < len(lines) and re.match(pattern, lines[index].strip()):
                items.append(re.sub(pattern, '', lines[index].strip())); index += 1
            tag = 'ol' if ordered else 'ul'
            result.append(f'<{tag}>' + ''.join('<li>' + html.escape(item) + '</li>' for item in items) + f'</{tag}>')
        elif line.startswith('>'):
            result.append('<blockquote>' + html.escape(line[1:].strip()) + '</blockquote>')
        else:
            result.append('<p>' + html.escape(line) + '</p>')
    return ''.join(result)


def render_export(folder, name, allowed):
    folder = Path(folder).resolve()
    if name not in allowed or Path(name).name != name or '/' in name or '\\' in name:
        raise FileNotFoundError('找不到可预览的交付文件')
    suffix = Path(name).suffix.lower()
    if suffix == '.docx':
        name = str(Path(name).with_suffix('.html'))
        if name not in allowed or not (folder / name).is_file():
            raise FileNotFoundError('该 Word 文件缺少对应预览，请重新生成答复包；原文件仍可下载。')
        suffix = '.html'
    if suffix not in ('.html', '.md', '.txt', '.csv', '.json'):
        raise ValueError('该格式仅供下载，请选择答复包中的文档预览。')
    path = (folder / name).resolve()
    if not path.is_relative_to(folder):
        raise PermissionError('无效预览文件路径')
    if path.stat().st_size > MAX_PREVIEW_BYTES:
        raise ValueError('该文件较大，请下载原文件查看。')
    content = path.read_bytes()
    if suffix == '.html':
        return content
    source = content.decode('utf-8-sig')
    if suffix == '.md':
        body = _markdown(source)
    elif suffix == '.csv':
        body = _table(list(csv.reader(io.StringIO(source))))
    else:
        if suffix == '.json':
            source = json.dumps(json.loads(source), ensure_ascii=False, indent=2)
        body = '<pre>' + html.escape(source) + '</pre>'
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
            '<title>' + html.escape(name) + '</title><style>'
            'body{margin:0 auto;padding:24px;max-width:1000px;font:15px/1.8 system-ui,"Microsoft YaHei",sans-serif;color:#252e2c;background:#fff;overflow-wrap:anywhere}'
            'h1{font-size:24px;line-height:1.4}h2{font-size:19px;margin:30px 0 12px}h3{font-size:16px;margin-top:24px}'
            'p,ul,ol{margin:14px 0}li{margin:7px 0}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}'
            'th,td{border:1px solid #d9ddd4;padding:9px 12px;text-align:left;vertical-align:top;min-width:80px}th{background:#efeee7}'
            'pre{white-space:pre-wrap;font:13px/1.7 Consolas,monospace}blockquote{margin:16px 0;padding:12px 16px;background:#f6f5f0}'
            '@media(max-width:500px){body{padding:16px;font-size:14px}h1{font-size:21px}}'
            '</style></head><body>' + body + '</body></html>').encode('utf-8')
