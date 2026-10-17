"""Bounded family discovery, document downloads and recoverable manual handoff."""
import json
import os
import re
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urljoin
from .retrieval import fetch_public, fetch_google_page, parse_google_patents, parse_ep_directory, Tree, validate_pdf, classify_document
from .storage import now
from . import ep_zip


def choose_cycle(documents):
    ordered = sorted([d for d in documents if d.get('date')], key=lambda d: d['date'], reverse=True)
    latest_oa = next((d for d in ordered if d.get('role') == 'oa'), None)
    responses = [d for d in ordered if d.get('role') == 'response']
    complete = [response for response in responses if any(d.get('role') == 'claims' and d.get('date') == response['date'] and d.get('application') == response.get('application') for d in ordered) and any(d.get('role') == 'oa' and d['date'] <= response['date'] and d.get('application') == response.get('application') for d in ordered)]
    response = next(iter(complete or responses), None)
    preceding = next((d for d in ordered if response and d.get('role') == 'oa' and d['date'] <= response['date'] and d.get('application') == response.get('application')), None)
    claims = [d for d in ordered if response and d.get('role') == 'claims' and d['date'] == response['date'] and d.get('application') == response.get('application')]
    return {'latest_oa': latest_oa, 'latest_response': next(iter(responses), None), 'response': response, 'response_oa': preceding, 'claims': claims, 'pairing_status': 'date-based candidate; source content still controls'}


def manual_guides(number, family, documents, target_country='BR'):
    guides = []
    countries = sorted({number[:2], target_country} | {m['country'] for m in family})
    for country in countries:
        members = [m for m in family if m['country'] == country]
        member = members[0] if members else {'publication': number if number[:2] == country else '', 'application': ''}
        application = member.get('application') or member.get('publication', '')
        if country == 'EP':
            app = ep_application(application)
            url = f'https://register.epo.org/application?number={app}&lng=en&tab=doclist' if app else 'https://register.epo.org/smartSearch?query=' + quote(application)
            instruction = '打开 All documents，选中所列文件，使用 Selected documents 或页面提供的 ZIP 下载；完成验证后下载并补传。'
        elif country == 'US':
            digits = re.sub(r'\D', '', member.get('application', ''))
            url = f'https://patentcenter.uspto.gov/applications/{digits}' if len(digits) == 8 else 'https://patentcenter.uspto.gov/'
            instruction = '在 Patent Center 按申请号查找 Documents & Transactions，下载最新 Non-Final/Final Rejection、对应 Applicant Arguments/Remarks、Amendment/Claims。未读到目录时无法确认具体日期。'
        elif country == 'BR':
            url = 'https://servicos.busca.inpi.gov.br/patentes/'
            instruction = f'在 INPI 按 {application} 检索，查 Despachos / Pareceres / Petições，下载本案审查意见、当前权项和相关答复；也可联系巴西代理所补件。'
        elif country == 'WO':
            url = 'https://patentscope.wipo.int/search/en/search.jsf'
            instruction = f'按 {application} 检索，查看 Documents，下载 ISR、WO/ISA、IPRP 以及 Art.19/34 修改；公开说明书不等于完整案卷。'
        elif country == 'CN':
            url = 'https://cpquery.cponline.cnipa.gov.cn/'
            instruction = '登录中国及多国专利审查信息查询系统，按申请号查询通知书、答复及权利要求版本。'
        else:
            url = member.get('url') or f'https://patents.google.com/patent/{quote(number)}/en'
            instruction = '从书目页进入本国官方案卷系统，下载最新实质审查意见、答复和当前权利要求；本版本没有该局专用案卷适配器。'
        files = [{'title': d['title'], 'date': d.get('date', ''), 'url': d.get('url', ''), 'status': d.get('status')} for d in documents if d.get('country') == country and d.get('role') in ('oa', 'response', 'claims') and d.get('status') not in ('downloaded', 'imported')]
        guides.append({'country': country, 'application': application, 'url': url, 'instruction': instruction, 'files': files, 'directory_verified': bool(files)})
    return guides


def ep_application(value):
    match = re.search(r'EP\s*(\d{8})', str(value))
    return 'EP' + match.group(1) if match else ''


def _download(store, case_id, doc, url, fetch):
    try:
        data, final, content_type = fetch(url)
        validate_pdf(data)
        meta = dict(doc, filename=f"{doc.get('country', 'XX')}-{doc.get('date') or 'undated'}-{doc['title'][:65]}.pdf", source_url=doc.get('url') or url)
        imported = store.import_document(case_id, data, meta)
        def replace(case):
            # Replace the discovery row while preserving the original identity used by selectors.
            original = next((d for d in case['documents'] if d['id'] == doc.get('id')), None)
            imported.update(status='downloaded', download_url=final)
            if original:
                original.update({k: v for k, v in imported.items() if k != 'id'})
                case['documents'] = [d for d in case['documents'] if d['id'] != imported['id']]
            else:
                next(d for d in case['documents'] if d['id'] == imported['id']).update(imported)
        store.update(case_id, replace)
        store.log(case_id, f"已下载 {doc['title']}（{len(data):,} 字节）")
        return True
    except Exception as exc:
        def failed(case):
            for row in case['documents']:
                if row['id'] == doc.get('id') and row.get('status') not in ('downloaded', 'imported'):
                    row.update(status='manual_required', notes=[f'自动下载失败：{type(exc).__name__}: {str(exc)[:200]}'])
        store.update(case_id, failed)
        store.log(case_id, f"{doc['title']} 未取得原件：{str(exc)[:180]}")
        return False


def ingest_google_page(store, case_id, html, url, fetch=fetch_public, download=True):
    parsed = parse_google_patents(html, url)
    if not parsed['publication']:
        raise ValueError('未识别到公开专利书目，可能是验证页或未找到该号码')
    def merge(case):
        if not case['title']:
            case['title'] = parsed['title']
        for member in parsed['family']:
            old = next((m for m in case['family'] if m['publication'] == member['publication']), None)
            if old:
                old.update({k: v for k, v in member.items() if v})
            else:
                case['family'].append(member)
        target = [m for m in case['family'] if m['country'] == case['target_country']]
        target_apps = {m.get('application') or m['publication'] for m in target}
        if not case['target_application'] and len(target_apps) == 1:
            case['target_application'] = next(iter(target_apps))
    store.update(case_id, merge)
    publication = parsed['publication']
    if parsed['pdf_url']:
        doc = store.add_discovered(case_id, {'title': publication + ' published specification', 'country': publication[:2], 'date': parsed['publication_date'], 'role': 'publication', 'version_status': 'granted' if re.search(r'B\d$', publication) else 'publication', 'language': 'unknown', 'url': parsed['pdf_url'], 'application': parsed['application'], 'publication': publication})
        existing = next(d for d in store.get(case_id)['documents'] if d['id'] == doc['id'])
        if download and existing['status'] not in ('downloaded', 'imported'):
            _download(store, case_id, doc, parsed['pdf_url'], fetch)
    return parsed


def _import_ep_zip(store, case_id, application, zip_path, rows):
    """Import a whole-dossier ZIP: match members to doclist rows (date + title),
    store each matched PDF under the row's identity, and report the rest."""
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith('.pdf')]
        matched = ep_zip.match_members(names, rows)
        count, skipped = 0, []
        for row in rows:
            name = matched.get(row['id'])
            if not name:
                continue
            current = next((d for d in store.get(case_id)['documents'] if d['id'] == row['id']), None)
            if current is None or current.get('status') in ('downloaded', 'imported'):
                continue
            data = zf.read(name)
            try:
                validate_pdf(data)
            except ValueError:
                skipped.append(name)
                continue
            parsed = ep_zip.parse_member_name(name) or {}
            meta = dict(row, filename=f"EP-{row.get('date') or 'undated'}-{row['title'][:65]}.pdf", source_url=row.get('url') or '')
            if current.get('role') == 'other':
                meta['role'] = ep_zip.role_for_member(parsed.get('codes', []), parsed.get('title', ''), classify_document)
            imported = store.import_document(case_id, data, meta)
            def replace(case, row_id=row['id'], imported=imported):
                original = next((d for d in case['documents'] if d['id'] == row_id), None)
                imported.update(status='downloaded', download_url=str(zip_path))
                if original:
                    original.update({k: v for k, v in imported.items() if k != 'id'})
                    case['documents'] = [d for d in case['documents'] if d['id'] != imported['id']]
            store.update(case_id, replace)
            count += 1
    leftover = [n for n in names if n not in matched.values()]
    if leftover:
        store.log(case_id, f'整包中 {len(leftover)} 件未能对应目录条目（标题截断或日期漂移），已保留 ZIP 原件供人工核对')
    if skipped:
        store.log(case_id, f'整包中 {len(skipped)} 件未通过 PDF 校验，未导入')
    return count


def research_ep(store, case_id, application, fetch):
    url = f'https://register.epo.org/application?number={application}&lng=en&tab=doclist'
    store.log(case_id, f'正在读取欧洲案卷目录 {application}')
    try:
        html, final = None, url
        try:
            raw, final, _ = fetch(url)
            candidate = raw.decode('utf-8', errors='replace')
            if 'documentId=' in candidate:
                html = candidate
            else:
                store.log(case_id, '欧洲案卷目录直接访问未取得有效内容（可能被人机验证拦截）')
        except Exception as exc:
            store.log(case_id, f'欧洲案卷目录直接访问失败：{str(exc)[:160]}')
        zip_path = None
        browser_enabled = os.environ.get('WORKBENCH_EP_BROWSER', '1') != '0'
        if html is None and browser_enabled:
            # 直连失败（典型：Cloudflare 拦截数据中心 IP）才回退浏览器整包下载。
            if ep_zip.available():
                try:
                    result = ep_zip.fetch_ep_dossier_via_browser(
                        application, store.case_dir(case_id) / 'downloads',
                        log=lambda m: store.log(case_id, m))
                    html = result['html'] or None
                    zip_path = result['zip']
                except Exception as exc:
                    store.log(case_id, f'浏览器整包下载未成功：{str(exc)[:200]}；转为逐件下载与人工补件')
            else:
                store.log(case_id, '未安装可选组件 playwright，跳过浏览器整包下载（pip install playwright && playwright install chromium 可启用）')
        if html is None:
            raise ValueError('欧洲案卷目录暂不可访问')
        docs = parse_ep_directory(html, application)
        if not docs:
            raise ValueError('未解析到目录文件，不能据此判断案卷为空')
        rows = [store.add_discovered(case_id, d) for d in docs]
        cycle = choose_cycle(rows)
        store.update(case_id, lambda c: c.setdefault('cycles', []).append({'application': application, 'source_url': final, 'retrieved_at': now(), 'directory_count': len(rows), 'latest_oa_id': (cycle['latest_oa'] or {}).get('id'), 'response_id': (cycle['response'] or {}).get('id'), 'response_oa_id': (cycle['response_oa'] or {}).get('id'), 'pairing_status': cycle['pairing_status']}))
        if zip_path:
            count = _import_ep_zip(store, case_id, application, zip_path, rows)
            store.log(case_id, f'欧洲案卷整包导入 {count} 件（共 {len(rows)} 项目录）')
        store.log(case_id, f'欧洲案卷目录 {len(rows)} 项；开始取得最新实质意见及最近答复轮次')
        selected = [cycle['latest_oa'], cycle['response'], cycle['latest_response'], cycle['response_oa']] + cycle['claims']
        seen = set()
        for doc in selected:
            if not doc or doc['id'] in seen:
                continue
            seen.add(doc['id'])
            if next(d for d in store.get(case_id)['documents'] if d['id'] == doc['id'])['status'] in ('downloaded', 'imported'):
                continue
            if doc['role'] == 'response':
                doc['cycle_id'] = doc['id']
            elif doc in cycle['claims'] or doc == cycle['response_oa']:
                doc['cycle_id'] = (cycle['response'] or {}).get('id', '')
            else:
                doc['cycle_id'] = ''
            if doc['role'] == 'claims':
                doc['version_status'] = 'reference'
            # Follow observed viewer iframe rather than guessing a PDF endpoint.
            try:
                body, viewer_url, content_type = fetch(doc['url'])
                if body.startswith(b'%PDF-'):
                    _download(store, case_id, doc, viewer_url, lambda u: (body, viewer_url, content_type))
                    continue
                tree = Tree(body.decode('utf-8', errors='replace')).root
                frames = tree.find(lambda n: n.tag in ('iframe', 'embed') and bool(n.attrs.get('src')))
                if not frames:
                    raise ValueError('已取得查看器页面，但未找到 PDF 内容地址')
                pdf_url = urljoin(viewer_url, frames[0].attrs['src'])
                _download(store, case_id, doc, pdf_url, fetch)
            except Exception as exc:
                def fail(c):
                    row = next(d for d in c['documents'] if d['id'] == doc['id'])
                    row.update(status='manual_required', notes=[str(exc)[:250]])
                store.update(case_id, fail)
                store.log(case_id, f"需手动下载 {doc['date']} {doc['title']}：{str(exc)[:120]}")
    except Exception as exc:
        store.log(case_id, f'欧洲案卷目录暂不可访问：{str(exc)[:200]}')


def research_case(store, case_id, fetch=fetch_public):
    case = store.get(case_id)
    number = case['input_number']
    store.update(case_id, lambda c: c.update(status='researching', last_error='', exports_stale=bool(c.get('exports'))))
    store.log(case_id, f'开始同族研究：{number}')
    try:
        parsed_pages = []
        try:
            raw, url, _ = fetch_google_page(number, fetch, log=lambda message: store.log(case_id, message))
            parsed_pages.append(ingest_google_page(store, case_id, raw.decode('utf-8', errors='replace'), url, fetch))
        except Exception as exc:
            store.update(case_id, lambda c: c.update(last_error=f'同族书目检索失败：{str(exc)[:220]}'))
            store.log(case_id, f'书目及同族自动检索未成功：{str(exc)[:220]}；可在浏览器查找并补充材料')
        family = store.get(case_id)['family']
        # Fetch one representative per application/country, preferring B documents for reference.
        ranked = sorted(family, key=lambda m: (m['country'] not in ('EP', case['target_country'], 'WO', 'US'), not bool(re.search(r'B\d$', m['publication']))))
        representatives, countries = [], set()
        for member in ranked:
            if member['country'] not in countries and member['publication'] != (parsed_pages[0]['publication'] if parsed_pages else ''):
                representatives.append(member)
                countries.add(member['country'])
        def fetch_member(member):
            data, final, _ = fetch(member['url'])
            return member, data.decode('utf-8', errors='replace'), final
        with ThreadPoolExecutor(max_workers=3) as pool:
            pending = {pool.submit(fetch_member, m): m for m in representatives[:6]}
            for future in as_completed(pending):
                member = pending[future]
                try:
                    _, html, final = future.result()
                    parsed_pages.append(ingest_google_page(store, case_id, html, final, fetch))
                except Exception as exc:
                    store.log(case_id, f"{member['publication']} 未取得：{str(exc)[:140]}")
        ep_apps = {ep_application(m.get('application', '')) for m in store.get(case_id)['family'] if m['country'] == 'EP'} - {''}
        for page in parsed_pages:
            for link in page['external_links']:
                if 'register.epo.org' in link:
                    match = re.search(r'(?:number|AP)=?(EP\d{8})', link)
                    if match:
                        ep_apps.add(match.group(1))
        for app in sorted(ep_apps)[:3]:
            research_ep(store, case_id, app, fetch)
        # Other portals have heterogeneous document/session APIs. Probe the real public entry
        # and capture observed PDF links; failures become instructions, not fabricated records.
        for member in [m for m in store.get(case_id)['family'] if m['country'] in ('BR', 'WO')][:2]:
            portal = 'https://servicos.busca.inpi.gov.br/patentes/' if member['country'] == 'BR' else 'https://patentscope.wipo.int/search/en/search.jsf'
            try:
                _, _, _ = fetch(portal)
                store.log(case_id, f"{member['country']} 官方入口可达；本版尚不能自动解析该局交互式案卷目录，请按指引补件")
            except Exception as exc:
                store.log(case_id, f"{member['country']} 官方入口访问失败：{str(exc)[:150]}")
    finally:
        current = store.get(case_id)
        guides = manual_guides(number, current['family'], current['documents'], current['target_country'])
        gaps = []
        if not current['family']:
            gaps.append('尚未核验同族；可手动查找后补充文件，不将查询失败解释为没有同族')
        if current.get('last_error'):
            gaps.append(current['last_error'])
        if not any(d.get('country') == current['target_country'] and d['role'] == 'oa' and d.get('text') for d in current['documents']):
            gaps.append('缺少本案可读取的审查意见')
        if not any(d.get('country') == current['target_country'] and d['role'] == 'claims' and d.get('version_status') == 'pending' for d in current['documents']):
            gaps.append('尚未锁定本案当前有效待审权项；不会将公开文本自动升级为 pending claims')
        store.update(case_id, lambda c: c.update(status='idle', manual_guides=guides, research_gaps=gaps, gaps=list(dict.fromkeys(gaps + (c.get('analysis') or {}).get('gaps', []))), researched_at=now()))
        store.log(case_id, '本轮检索结束；可查看取得的原件、补件清单，或直接生成现有材料的草案包')
