"""EP Register full-dossier ZIP download via a real browser (optional Playwright).

Why a browser: register.epo.org sits behind Cloudflare. Plain HTTP clients and
headless automation from low-reputation IPs get a "Just a moment..." challenge
(HTTP 403) and never see the dossier. A *headed* Chromium window passes the
challenge automatically on normal networks, and a human can complete it in the
worst case. Single-document links are rate-limited; the dossier "Zip archive"
button downloads everything in one request, so this module prefers the ZIP.

Playwright is an optional dependency: the rest of the workbench runs without it.
Install with:  pip install playwright
The system Chromium/Chrome is used when present; otherwise run once:
python -m playwright install chromium
"""
import os
import re
import shutil
import zipfile
from pathlib import Path

EP_DOCLIST = 'https://register.epo.org/application?number={app}&lng=en&tab=doclist'
CF_WAIT_ROUNDS = 120          # 120 x 5s = 10 min; covers auto-pass and manual checkbox
DOWNLOAD_TIMEOUT_MS = 300000  # ZIP of a full dossier can take a while to build
_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

# Document-code hints from EP Register ZIP member names, e.g.
# 21934362-2024-11-21-1503SS-Supplementary European search report.pdf
EP_CODE_ROLES = {
    '1503SS': 'oa', '1703': 'oa', '1224': 'oa', '1503': 'oa',
    'ABEX': 'response', 'MEPA': 'response',
    'CLMS': 'claims', 'CLMSABEX': 'claims', 'CLMS-HWA': 'claims',
    'ISR': 'oa', 'IPRP': 'oa',
}


class EpZipError(RuntimeError):
    """Actionable failure: the caller turns this into a manual-download guide."""


def available():
    """True when the optional Playwright dependency is importable."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except Exception:
        return False


def _chromium_executable():
    for name in ('chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable', 'chrome'):
        path = shutil.which(name)
        if path:
            return path
    for candidate in (
        os.environ.get('PROGRAMFILES', '') + r'\Google\Chrome\Application\chrome.exe',
        os.environ.get('PROGRAMFILES(X86)', '') + r'\Google\Chrome\Application\chrome.exe',
        os.environ.get('LOCALAPPDATA', '') + r'\Google\Chrome\Application\chrome.exe',
        os.environ.get('PROGRAMFILES', '') + r'\Microsoft\Edge\Application\msedge.exe',
    ):
        if candidate and Path(candidate).exists():
            return candidate
    return None


def _proxy_from_env():
    for var in ('HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy'):
        value = os.environ.get(var)
        if value:
            return {'server': value}
    return None


def _looks_blocked(page):
    try:
        title = page.title().lower()
    except Exception:
        return True  # mid-navigation; keep waiting
    return 'just a moment' in title or 'attention required' in title


def _wait_for_challenge(page, log):
    """Wait out the Cloudflare interstitial; the user may solve it by hand."""
    for _ in range(CF_WAIT_ROUNDS):
        try:
            if not _looks_blocked(page):
                page.wait_for_load_state('domcontentloaded', timeout=30000)
                return
        except Exception:
            pass  # navigation in progress; keep polling
        page.wait_for_timeout(5000)
    raise EpZipError('欧洲专利局站点的人机验证未在 10 分钟内通过；请在弹出的浏览器窗口中完成验证后重试，'
                     '或改用手动下载指引')


def _select_all(page, log):
    """Tick the doclist header checkbox (and every row checkbox)."""
    page.wait_for_selector('a[href*="documentId="]', timeout=60000)
    checked = page.evaluate("""() => {
        const boxes = Array.from(document.querySelectorAll('table input[type=checkbox]'));
        if (!boxes.length) return 0;
        const inHeader = boxes.filter(b => b.closest('th'));
        const master = inHeader[0] || boxes[0];
        master.click();
        const all = Array.from(document.querySelectorAll('table input[type=checkbox]'));
        all.forEach(b => { if (!b.checked) b.click(); });
        return all.length;
    }""")
    if not checked:
        raise EpZipError('未在案卷目录页找到文件选择框；页面结构可能已改版')
    log(f'欧洲案卷目录已全选 {checked} 个文件，请求整包 ZIP')


def _click_zip(page):
    """Click the dossier 'Zip archive' control. Caller must have already armed
    expect_download — the event fires the moment the click lands."""
    target = page.evaluate("""() => {
        const els = Array.from(document.querySelectorAll('a,button,input,span[role=button]'));
        const hit = els.find(e => /zip/i.test(((e.innerText||'') + ' ' + (e.value||'') + ' ' +
            (e.getAttribute('title')||'') + ' ' + (e.getAttribute('aria-label')||''))));
        if (!hit) return false;
        hit.scrollIntoView(); hit.click(); return true;
    }""")
    if not target:
        raise EpZipError('未找到 Zip archive 下载入口；页面结构可能已改版')


def fetch_ep_dossier_via_browser(application, dest_dir, log=print, headless=None):
    """Open the EP Register dossier in a real browser window, pass the challenge,
    select all documents and download the whole dossier as one ZIP.

    Returns {'html': str, 'zip': Path}. Raises EpZipError with a user-facing
    message on failure. The browser window is visible by default on purpose:
    Cloudflare passes headed sessions far more often, and a visible window lets
    the user complete a stubborn challenge manually. Set workbench env
    WORKBENCH_EP_HEADLESS=1 to force headless mode.
    """
    if not available():
        raise EpZipError('未安装浏览器组件 playwright；运行 pip install playwright 后重试')
    from playwright.sync_api import sync_playwright

    app = application if str(application).upper().startswith('EP') else 'EP' + re.sub(r'\D', '', str(application))
    if not re.fullmatch(r'EP\d{8}', app):
        raise EpZipError(f'欧洲申请号格式无法识别：{application}')
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    if headless is None:
        if os.environ.get('WORKBENCH_EP_HEADLESS') == '1':
            headless = True
        else:
            # Headed windows pass Cloudflare far more often; fall back to
            # headless only where no display exists (CI, servers).
            headless = bool(os.name != 'nt' and os.sys.platform != 'darwin'
                            and not os.environ.get('DISPLAY'))
    launch_args = {'headless': headless,
                   'args': ['--disable-blink-features=AutomationControlled', '--disable-dev-shm-usage']}
    executable = _chromium_executable()
    if executable:
        launch_args['executable_path'] = executable
    proxy = _proxy_from_env()
    if proxy:
        launch_args['proxy'] = proxy

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_args)
        try:
            context = browser.new_context(accept_downloads=True, user_agent=_UA,
                                          viewport={'width': 1366, 'height': 900}, locale='en-US')
            page = context.new_page()
            log(f'正在打开欧洲案卷 {app}（如弹出浏览器窗口出现人机验证，请完成一次即可）')
            page.goto(EP_DOCLIST.format(app=app), timeout=90000, wait_until='domcontentloaded')
            _wait_for_challenge(page, log)
            page.wait_for_load_state('networkidle', timeout=60000)
            page.wait_for_timeout(2000)
            html = page.content()
            if 'documentId=' not in html:
                raise EpZipError('已进入欧洲案卷页但未读到文件目录；请核对申请号或稍后重试')
            _select_all(page, log)
            with page.expect_download(timeout=DOWNLOAD_TIMEOUT_MS) as pending:
                _click_zip(page)
            download = pending.value
            zip_path = dest / f'{app}-dossier.zip'
            download.save_as(str(zip_path))
        finally:
            browser.close()
    validate_zip(zip_path)
    log(f'欧洲案卷整包已下载：{zip_path.name}（{zip_path.stat().st_size:,} 字节）')
    return {'html': html, 'zip': zip_path}


def validate_zip(path):
    path = Path(path)
    with open(path, 'rb') as fh:
        if fh.read(4) != b'PK\x03\x04':
            raise EpZipError('下载结果不是 ZIP（可能为验证页或限流响应）')
    with zipfile.ZipFile(path) as zf:
        bad = zf.testzip()
        if bad:
            raise EpZipError(f'ZIP 内部损坏于 {bad}')
        pdfs = [n for n in zf.namelist() if n.lower().endswith('.pdf')]
        if not pdfs:
            raise EpZipError('ZIP 中没有 PDF 文件')


def parse_member_name(name):
    """'21934362-2024-11-21-1503SS-Supplementary European search report.pdf'
    -> {'date': '2024-11-21', 'code': '1503SS', 'title': 'Supplementary ...'}

    Register codes are glued before the title and vary in shape ('1201-1',
    'RECEIPT-OLF', 'CLMS-HWA', '2906I'). Split on '-', drop leading ALL-CAPS /
    numeric tokens as codes, and treat the first mixed-case token as the start
    of the title.
    """
    base = Path(name).name
    parts = base[:-4].split('-') if base.lower().endswith('.pdf') else []
    if len(parts) < 5 or not re.fullmatch(r'\d{7,9}', parts[0]):
        return None
    if not (re.fullmatch(r'\d{4}', parts[1]) and re.fullmatch(r'\d{2}', parts[2]) and re.fullmatch(r'\d{2}', parts[3])):
        return None
    date = f'{parts[1]}-{parts[2]}-{parts[3]}'
    rest, codes = parts[4:], []
    while rest and re.fullmatch(r'[A-Z0-9]+', rest[0]):
        codes.append(rest.pop(0))
    if not rest:
        return None
    return {'date': date, 'code': codes[0] if codes else '', 'codes': codes,
            'title': ' '.join('-'.join(rest).split())}


def role_for_member(codes, title, classify):
    """Document-code hint first (it is authoritative EP metadata), title fallback."""
    for code in codes if isinstance(codes, (list, tuple)) else [codes]:
        if code in EP_CODE_ROLES:
            return EP_CODE_ROLES[code]
        if code.startswith('CLMS'):
            return 'claims'
    return classify(title)


def _norm(text):
    return re.sub(r'[^a-z0-9]+', ' ', str(text).lower()).strip()


def match_members(member_names, docs):
    """Match ZIP members to doclist rows. Returns {doc_id: member_name}.
    Rows carry an ISO date and the Register's own title; member titles are the
    same strings (truncated), so date + normalized-prefix equality is safe."""
    by_date = {}
    for name in member_names:
        parsed = parse_member_name(name)
        if parsed:
            by_date.setdefault(parsed['date'], []).append((name, parsed))
    matched, used = {}, set()
    for doc in docs:
        date = doc.get('date') or ''
        title = _norm(doc.get('title', ''))
        if not title:
            continue
        for name, parsed in by_date.get(date, []):
            if name in used:
                continue
            member_title = _norm(parsed['title'])
            if member_title and (member_title.startswith(title[:60]) or title.startswith(member_title[:60])):
                matched[doc['id']] = name
                used.add(name)
                break
    return matched
