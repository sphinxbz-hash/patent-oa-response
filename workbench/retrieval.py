"""Public-source access and parsers. Responses remain evidence, never instructions."""
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.error import URLError, HTTPError
from html.parser import HTMLParser
from urllib.parse import urlparse, urljoin, parse_qs, quote
from urllib.request import Request, build_opener, HTTPRedirectHandler
from datetime import datetime

MAX_BYTES = 25 * 1024 * 1024
ALLOWED_HOSTS = ('patents.google.com', 'patentimages.storage.googleapis.com', 'epo.org', 'wipo.int', 'inpi.gov.br', 'uspto.gov', 'cnipa.gov.cn', 'gov.br')


def validate_public_url(url):
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('只允许官方专利站点及公开专利镜像的 HTTPS 地址')
    if not any(host == domain or host.endswith('.' + domain) for domain in ALLOWED_HOSTS):
        raise ValueError('下载地址不在支持的公开专利来源范围内')
    return url


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _urllib_fetch(url, timeout=12, data=None):
    validate_public_url(url)
    request = Request(url, data=data, headers={'User-Agent': 'PatentFamilyWorkbench/0.1 (public document research)', 'Accept': 'text/html,application/pdf,application/json,*/*'})
    with build_opener(SafeRedirect()).open(request, timeout=timeout) as response:
        if int(response.headers.get('Content-Length', '0') or '0') > MAX_BYTES:
            raise ValueError('文件超过 25 MB，请通过浏览器下载后分件导入')
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError('文件超过 25 MB')
        return body, response.geturl(), response.headers.get('Content-Type', '')


def _curl_fetch(url, timeout=12, data=None, redirects=0):
    """Use the OS TLS stack when Python TLS cannot establish the public connection."""
    validate_public_url(url)
    executable = shutil.which('curl.exe') or shutil.which('curl')
    if not executable:
        raise OSError('Python TLS 连接失败，系统未安装备用下载工具 curl')
    with tempfile.TemporaryDirectory(prefix='patent-download-') as folder:
        output, headers = Path(folder) / 'body', Path(folder) / 'headers'
        args = [executable, '--silent', '--show-error', '--max-time', str(timeout), '--connect-timeout', '8', '--max-filesize', str(MAX_BYTES), '--proto', '=https', '--output', str(output), '--dump-header', str(headers), '--write-out', '%{http_code}', '--user-agent', 'PatentFamilyWorkbench/0.1', url]
        if data is not None:
            args.extend(['--data-binary', '@-'])
        process = subprocess.run(args, input=data, capture_output=True, timeout=timeout + 3)
        if process.returncode:
            raise OSError(process.stderr.decode('utf-8', errors='replace')[:300])
        status = int(process.stdout.decode().strip() or '0')
        header_text = headers.read_text(encoding='latin1')
        if status in (301, 302, 303, 307, 308):
            locations = re.findall(r'^location:\s*(.+)$', header_text, re.I | re.M)
            if not locations or redirects >= 3:
                raise ValueError('下载重定向次数过多或缺少地址')
            target = urljoin(url, locations[-1].strip())
            validate_public_url(target)
            return _curl_fetch(target, timeout, data if status in (307, 308) else None, redirects + 1)
        if status != 200:
            raise OSError(f'HTTP {status}，服务器未返回可用内容')
        if output.stat().st_size > MAX_BYTES:
            raise ValueError('文件超过 25 MB')
        types = re.findall(r'^content-type:\s*(.+)$', header_text, re.I | re.M)
        return output.read_bytes(), url, types[-1].strip() if types else ''


def fetch_public(url, timeout=12, data=None):
    try:
        return _urllib_fetch(url, timeout, data)
    except (URLError, OSError) as exc:
        if isinstance(exc, HTTPError) or not any(word in str(exc).upper() for word in ('SSL', 'TLS', 'EOF')):
            raise
        return _curl_fetch(url, timeout, data)


def validate_pdf(data):
    if not data.lstrip().startswith(b'%PDF-') or b'%%EOF' not in data[-4096:]:
        raise ValueError('返回内容不是完整 PDF（可能为验证页、限流或错误页）')


class Node:
    def __init__(self, tag='', attrs=None):
        self.tag, self.attrs, self.children = tag, dict(attrs or []), []

    def text(self):
        return ''.join(c if isinstance(c, str) else c.text() for c in self.children)

    def find(self, predicate):
        result = [self] if predicate(self) else []
        for child in self.children:
            if isinstance(child, Node):
                result.extend(child.find(predicate))
        return result


class Tree(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node('root')
        self.stack = [self.root]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in ('area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'):
            self.stack.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                self.stack = self.stack[:i]
                break

    def handle_data(self, text):
        self.stack[-1].children.append(text)


def prop(node, name):
    nodes = node.find(lambda n: name in n.attrs.get('itemprop', '').split())
    return (nodes[0].attrs.get('content') or nodes[0].text()).strip() if nodes else ''


def classify_document(title):
    title = title.lower()
    if re.match(r'^(?:\(electronic\)\s*)?receipt\b', title) or any(t in title for t in ('fee', 'translation', 'certificate', 'intention to grant', 'decision to grant', 'invitation to declare maintenance')):
        return 'other'
    if any(t in title for t in ('reply', 'response', 'observations', 'resposta')) and 'claim' not in title:
        return 'response'
    if any(t in title for t in ('search opinion', 'examination report', 'communication pursuant to article 94', 'communication under article 94', 'non-final', 'non final', 'final rejection', 'written opinion', 'parecer', 'exigência')):
        return 'oa'
    if 'claim' in title or 'reivindica' in title:
        return 'claims'
    if any(t in title for t in ('reply', 'response', 'amendments received', 'observations', 'resposta')):
        return 'response'
    return 'other'


def parse_google_patents(html, source_url):
    root = Tree(html).root
    current_pub = prop(root, 'publicationNumber')
    current_app = prop(root, 'applicationNumber')
    title = prop(root, 'title')
    if not title:
        titles = root.find(lambda n: n.tag == 'title')
        title = titles[0].text().strip() if titles else ''
    family = []
    # Only explicit family tables; citations and similar documents are deliberately excluded.
    rows = root.find(lambda n: n.tag == 'tr' and n.attrs.get('itemprop') in ('countryStatus', 'docdbFamily', 'familyToFamily'))
    for row in rows:
        links = row.find(lambda n: n.tag == 'a' and '/patent/' in n.attrs.get('href', ''))
        publication = prop(row, 'representativePublication') or prop(row, 'publicationNumber')
        if not publication and links:
            match = re.search(r'/patent/([A-Z]{2}\d+[A-Z]\d?)', links[0].attrs['href'])
            publication = match.group(1) if match else ''
        if publication and not any(f['publication'] == publication for f in family):
            family.append({'country': publication[:2], 'publication': publication, 'application': prop(row, 'applicationNumber'), 'status': '', 'status_source': '', 'url': f'https://patents.google.com/patent/{publication}/en'})
    if current_pub and not any(f['publication'] == current_pub for f in family):
        family.insert(0, {'country': current_pub[:2], 'publication': current_pub, 'application': current_app, 'status': prop(root, 'status'), 'status_source': source_url, 'url': source_url})
    for node in root.find(lambda n: n.tag == 'li' and bool(prop_shallow(n, 'applicationNumber'))):
        application = prop(node, 'applicationNumber')
        status = prop(node, 'legalStatus')
        document = prop(node, 'documentId')
        for member in family:
            if member['publication'] in document:
                member.update(application=application, status=status, status_source=source_url)
    for member in family:
        if member['publication'] == current_pub:
            member['application'] = current_app
    pdfs = root.find(lambda n: (n.tag == 'meta' and n.attrs.get('name') == 'citation_pdf_url') or n.attrs.get('itemprop') == 'pdfLink')
    pdf_url = (pdfs[0].attrs.get('content') or pdfs[0].attrs.get('href') or pdfs[0].text()).strip() if pdfs else ''
    # Texts from Google may be machine translated; never promote them to filed English claims.
    claim_nodes = root.find(lambda n: n.attrs.get('itemprop') == 'claim')
    claims = '\n'.join(n.text().strip() for n in claim_nodes)
    external = [urljoin(source_url, n.attrs['href']) for n in root.find(lambda n: n.tag == 'a' and any(h in n.attrs.get('href', '') for h in ('register.epo.org', 'patentscope.wipo.int', 'patentcenter.uspto.gov')))]
    return {'publication': current_pub, 'application': current_app, 'title': title, 'family': family, 'pdf_url': pdf_url, 'claims': claims, 'external_links': external, 'publication_date': prop(root, 'publicationDate'), 'filing_date': prop(root, 'filingDate')}


def prop_shallow(node, name):
    return any(isinstance(c, Node) and c.attrs.get('itemprop') == name for c in node.children)


def _identifier_key(value):
    # Punctuation and a document kind suffix are not part of the serial number.
    # The application serial itself is retained (including EP/CN check digits).
    compact = re.sub(r'[^A-Z0-9]', '', str(value).upper())
    return re.sub(r'(?<=\d)[A-Z]\d?$', '', compact)


def fetch_google_page(number, fetch=fetch_public, log=lambda message: None):
    """Resolve an application to a publication using observed search metadata.

    Search ranking alone is never evidence of identity. Confirm the input against
    the publication page's own application/publication fields before ingestion.
    """
    initial = f'https://patents.google.com/patent/{quote(number, safe="")}/en'
    try:
        result = fetch(initial)
        parsed = parse_google_patents(result[0].decode('utf-8', errors='replace'), result[1])
        if parsed['publication'] and any(_identifier_key(number) == _identifier_key(parsed[key])
                                         for key in ('publication', 'application')):
            return result
        raise ValueError('直达页未返回与输入号码对应的公开书目')
    except Exception as exc:
        log(f'号码直达页未取得：{str(exc)[:160]}；正在查询对应公开号')

    search_url = 'https://patents.google.com/xhr/query?url=' + quote('q=' + number, safe='') + '&exp='
    raw, _, _ = fetch(search_url)
    payload = json.loads(raw.decode('utf-8'))
    candidates = []
    for cluster in payload.get('results', {}).get('cluster', []):
        for hit in cluster.get('result', []):
            publication = hit.get('patent', {}).get('publication_number', '')
            if (not hit.get('is_similar_document') and
                    re.fullmatch(r'[A-Z]{2}\d{5,16}[A-Z]\d?', publication) and
                    publication not in candidates):
                candidates.append(publication)
    for publication in candidates[:3]:
        url = f'https://patents.google.com/patent/{publication}/en'
        try:
            result = fetch(url)
            parsed = parse_google_patents(result[0].decode('utf-8', errors='replace'), result[1])
            if parsed['publication'] == publication and any(
                    _identifier_key(number) == _identifier_key(parsed[key])
                    for key in ('publication', 'application')):
                log(f'通过申请号查询确认公开号：{number} → {publication}；书目：{result[1]}')
                return result
        except Exception as exc:
            log(f'候选公开号 {publication} 未核验：{str(exc)[:120]}')
    raise ValueError(f'未找到与 {number} 精确对应的公开书目；请核对号码或补充公开号，不将相似结果当作同族')


def parse_ep_directory(html, application):
    root = Tree(html).root
    result, seen = [], set()
    for row in root.find(lambda n: n.tag == 'tr'):
        links = row.find(lambda n: n.tag == 'a' and 'documentId=' in n.attrs.get('href', ''))
        for link in links:
            match = re.search(r'documentId=([A-Za-z0-9]+)', link.attrs['href'])
            if not match or match.group(1) in seen:
                continue
            docid = match.group(1)
            date_match = re.search(r'(?<!\d)(\d{2}\.\d{2}\.\d{4})(?!\d)', row.text())
            date = datetime.strptime(date_match.group(1), '%d.%m.%Y').date().isoformat() if date_match else ''
            title = ' '.join(link.text().split())
            if not title:
                continue
            result.append({'remote_id': docid, 'country': 'EP', 'application': application, 'title': title, 'date': date, 'role': classify_document(title), 'status': 'discovered', 'url': f'https://register.epo.org/application?documentId={docid}&number={application}&lng=en&npl=false', 'version_status': 'unknown', 'language': 'unknown', 'requires_clean_text': bool(re.search(r'annotations|marked[- ]?up|tracked changes', title, re.I))})
            seen.add(docid)
    return result
