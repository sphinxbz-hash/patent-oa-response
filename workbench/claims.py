"""Lossless text comparison and conservative patent identifiers."""
import re
from difflib import SequenceMatcher


def normalize_number(value):
    value = str(value).strip().upper()
    if not value or len(value) > 60 or re.search(r'[^A-Z0-9\s./,\-]', value):
        raise ValueError('请输入包含法域前缀的申请号或公开号，例如 BR112023019754A2')
    if '..' in value:
        raise ValueError('申请号格式不正确')
    if re.fullmatch(r'\d{2}/\d{3},?\d{3}', value):
        value = 'US' + value
    if value.startswith('PCT/'):
        return re.sub(r'[\s,\-]', '', value)
    if value.startswith('BR'):
        value = re.sub(r'(?<=\d)-\d(?=\s*(?:[A-Z]\d?)?$)', '', value)
    compact = re.sub(r'[\s./,\-]', '', value)
    if not re.fullmatch(r'[A-Z]{2}\d{5,16}[A-Z]?\d?', compact):
        raise ValueError('请输入法域前缀及完整号码，例如 CN117691670A 或 US18/279065')
    return compact


def parse_claims(text):
    """Read numbered plain text without changing technical signs or wording."""
    text = str(text or '').replace('\r\n', '\n').replace('\r', '\n')
    starts = list(re.finditer(r'^\s*(\d{1,3})\s*[.)]\s*(?:\((?:Original|Currently amended|Previously presented|New|Canceled|Withdrawn|Not entered)\)\s*)?', text, re.M | re.I))
    # OCR can put the endpoint of "claims 1 to 2." on a line by itself.
    # Preserve that endpoint as content, rather than dropping an empty claim.
    starts = [m for m in starts if not (
        re.match(r'[ \t]*\d{1,3}[ \t]*[.)][ \t]*(?:\n|$)',text[m.start():].lstrip('\n'))
        and re.search(r'\b(?:claim|claims?\s+\d+\s+(?:to|and|or))\s*$',text[:m.start()].rstrip(),re.I))]
    result = []
    for index, match in enumerate(starts):
        number = int(match.group(1))
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        body = text[match.end():end].strip()
        if number and body:
            if any(c['number'] == number for c in result):
                raise ValueError('权项编号重复；请提供单一语言、单一版本的权利要求文本')
            result.append({'number': number, 'text': body})
    return result


def diff_tokens(before, after):
    # Keep whitespace and symbols as separate tokens so both versions reconstruct exactly.
    left = re.findall(r'\w+|\s+|[^\w\s]', str(before), re.UNICODE)
    right = re.findall(r'\w+|\s+|[^\w\s]', str(after), re.UNICODE)
    result = []
    for tag, i, j, a, b in SequenceMatcher(None, left, right, autojunk=False).get_opcodes():
        if tag == 'equal':
            result.append(('equal', ''.join(left[i:j])))
        else:
            if tag in ('replace', 'delete'):
                result.append(('delete', ''.join(left[i:j])))
            if tag in ('replace', 'insert'):
                result.append(('insert', ''.join(right[a:b])))
    return result
