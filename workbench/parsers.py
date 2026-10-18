"""Optional document parsers, isolated from the workbench's Python environment."""
import hashlib
import io
import json
import os
import re
import subprocess
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKENDS = {'docling_tesseract': ('docling', 'Docling 版面 + 双引擎核对'),
            'paddle_structure': ('paddle', 'PaddleOCR 英文文档解析')}
FURNITURE = {'page_header', 'page_footer', 'page_number', 'header', 'footer', 'header_image', 'footer_image'}


def tool_root():
    return Path(os.environ.get('WORKBENCH_OCR_TOOLS') or ROOT / 'workbench-data/tools').resolve()


def tesseract_command():
    import shutil
    candidates = [tool_root()/'tesseract/tesseract.exe',
                  Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Tesseract-OCR/tesseract.exe']
    return next((str(p) for p in candidates if p.is_file()), shutil.which('tesseract') or 'tesseract')


def backend_version(backend):
    if backend not in BACKENDS:
        raise ValueError('未知英文材料解析器')
    path = tool_root() / BACKENDS[backend][0] / 'manifest.json'
    try:
        manifest = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        manifest = {'installed': False}
    config = dict(backend=backend, protocol=11 if backend=='docling_tesseract' else 8, language='eng', layout_cleanup=3,
                  render_dpi=300, generative_enrichment=False, manifest=manifest)
    if backend=='docling_tesseract':
        from .ocr import cache_version
        config['verification_ocr']=cache_version()
    digest = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:16]
    return backend + '-v1-' + digest


def backend_status():
    result = [{'id':'rapidocr', 'label':'现有多语种识别', 'installed':True}]
    for backend, (folder, label) in BACKENDS.items():
        runtime = tool_root() / folder / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        result.append(dict(id=backend, label=label, installed=runtime.is_file() and
                           (runtime.parent.parent / 'manifest.json').is_file()))
    return result


def default_backend(data_root=None):
    """A local evaluated preference never makes optional packages mandatory."""
    try:
        preference=(Path(data_root)/'tools' if data_root is not None else tool_root())/'default-parser.json'
        selected=json.loads(preference.read_text(encoding='utf-8'))['engine']
        if any(b['id']==selected and b['installed'] for b in backend_status()):return selected
    except (OSError,ValueError,KeyError,TypeError):pass
    return 'rapidocr'


def normalize_layout(blocks, sizes):
    """Retain raw blocks and their reading order; make exclusions auditable."""
    repeated={}
    gutter=[]
    for number,size in sizes.items():
        these=[b for b in blocks if int(b['page'])==int(number)]
        for b in these:
            box=b.get('bbox');text=str(b.get('text') or '').strip()
            if box and text and box[3]<float(size['height'])*.1:
                key=(re.sub(r'\d+','#',text),round(box[0]/float(size['width']),1))
                repeated.setdefault(key,set()).add(int(number))
        nums=sorted([b for b in these if b.get('label')=='text' and b.get('bbox')
                     and re.fullmatch(r'\d{1,3}',str(b.get('text') or '').strip())
                     and 5<=int(b['text'])<=200 and int(b['text'])%5==0
                     and 0<=b['bbox'][0]<=b['bbox'][2]<float(size['width'])*.12],key=lambda b:b['bbox'][1])
        for start in range(len(nums)-2):
            seq=nums[start:start+3]
            if (all(0<int(seq[j+1]['text'])-int(seq[j]['text'])<=15 for j in (0,1))
                    and max(b['bbox'][0] for b in seq)-min(b['bbox'][0] for b in seq)<float(size['width'])*.01):
                gutter.extend((b['bbox'][0]/size['width'],b['bbox'][2]/size['width']) for b in seq)
    claim_heading=next((b for b in blocks if int(b['page'])==1 and b.get('bbox')
                       and str(b.get('text') or '').strip().lower()=='claims'
                       and b.get('label')=='section_header'),None)
    claim_document=bool(claim_heading and any(int(b['page'])==1 and
        re.match(r'^1[.)]\s+[A-Za-z]',str(b.get('text') or '')) for b in blocks))
    pages = []
    for number, size in sorted(sizes.items(), key=lambda p:int(p[0])):
        page_blocks = [dict(b) for b in blocks if int(b['page']) == int(number)]
        right=[b for b in page_blocks if b.get('bbox') and b['bbox'][0]>=float(size['width'])*.74]
        right_text=' '.join(str(b.get('text') or '') for b in right)
        contact_column=bool(re.search(r'www\.|\S+@\S+',right_text,re.I)
            and re.search(r'attorne|patentanw|rechtsanw',right_text,re.I)
            and any(re.search(r'in response|respectfully|dear sir',str(b.get('text') or ''),re.I)
                    for b in page_blocks if b not in right))
        opening=next((b['bbox'][1] for b in page_blocks if b.get('bbox') and
                      re.match(r'in response\b',str(b.get('text') or ''),re.I)),None)
        footer_text=' '.join(str(b.get('text') or '') for b in page_blocks if b.get('bbox')
                             and b['bbox'][1]>float(size['height'])*.9)
        # A number near the margin is not sufficient evidence: it may be a
        # claim marker or a technical value. Require a repeated gutter sequence.
        candidates = [(i,b) for i,b in enumerate(page_blocks)
                      if str(b.get('label') or '').lower() == 'text'
                      and re.fullmatch(r'\d{1,3}', str(b.get('text') or '').strip())
                      and b.get('bbox') and 5 <= int(b['text']) <= 200
                      and int(b['text']) % 5 == 0
                      and 0 <= b['bbox'][0] <= b['bbox'][2] < float(size['width']) * .12]
        counters = set()
        candidates.sort(key=lambda pair:pair[1]['bbox'][1])
        for start in range(len(candidates)-2):
            sequence = candidates[start:start+3]
            if (all(int(sequence[j+1][1]['text'])-int(sequence[j][1]['text']) == 5 for j in (0,1))
                    and max(b['bbox'][0] for _,b in sequence)-min(b['bbox'][0] for _,b in sequence) < float(size['width'])*.01
                    and all(sequence[j+1][1]['bbox'][1] > sequence[j][1]['bbox'][3] for j in (0,1))):
                counters.update(i for i,_ in sequence)
        body, excluded = [], []
        for index, block in enumerate(page_blocks):
            text = str(block.get('text') or '').strip()
            label = str(block.get('label') or '').lower()
            box = block.get('bbox')
            reason = 'layout_' + label if label in FURNITURE else ''
            if not reason and box:
                key=(re.sub(r'\d+','#',text),round(box[0]/float(size['width']),1))
                if (box[3]<float(size['height'])*.1 and len(text)<100 and
                        box[3]-box[1]<float(size['height'])*.04 and
                        sum(len(pages)>=2 for pages in repeated.values())>=3 and
                        len(repeated.get(key,set()))>=2):
                    reason='repeated_header'
                elif claim_document and int(number)==1 and box[3]<claim_heading['bbox'][1]:
                    reason='claim_document_letterhead'
                elif (claim_document and box[1]>float(size['height'])*.9
                      and box[2]-box[0]<float(size['width'])*.2
                      and re.fullmatch(r'[-–—\d\s/]+',text)
                      and re.search(r'\d+\s*/\s*\d+',footer_text)):
                    reason='claim_document_page_footer'
                elif contact_column and block in right:
                    reason='letter_contact_column'
                elif contact_column and opening is not None and box[3]<opening:
                    reason='letter_envelope'
                elif (label=='text' and gutter and re.fullmatch(r'\d{1,3}',text)
                        and 0<=int(text)<=200 and any(abs(box[0]/size['width']-left)<.015
                        and abs(box[2]/size['width']-right)<.015 for left,right in gutter)):
                    reason='left_margin_line_number'
            if not reason and index in counters:
                reason = 'left_margin_line_number'
            if reason:
                excluded.append(dict(block, reason=reason))
            elif text:
                body.append(text)
        raw = '\n'.join(str(b.get('raw_text',b.get('text')) or '').strip() for b in page_blocks if str(b.get('raw_text',b.get('text')) or '').strip())
        pages.append(dict(number=int(number), text=raw, body_text='\n'.join(body),
                          blocks=page_blocks, excluded_blocks=excluded, method='ocr',
                          quality='unverified', page_size=size))
    return dict(text='\n\n'.join(p['text'] for p in pages),
                body_text='\n\n'.join(p['body_text'] for p in pages), pages=pages,
                status='complete' if all(p['body_text'].strip() for p in pages) else 'partial',
                notes=['OCR：正文已按版面分区提取，排除项与坐标保留；未人工逐字核验。'],
                ocr_pages=len(pages), native_pages=0, failed_pages=[],
                review_pages=[p['number'] for p in pages], empty_pages=[p['number'] for p in pages if not p['body_text'].strip()])


def run_worker(data, folder, backend):
    runtime = tool_root() / BACKENDS[backend][0] / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not runtime.is_file():
        raise RuntimeError('未安装 ' + BACKENDS[backend][1] + '；请运行专用组件安装脚本')
    folder.mkdir(parents=True, exist_ok=True)
    request = folder / (uuid.uuid4().hex + '.pdf')
    response = request.with_suffix('.json')
    log = request.with_suffix('.log')
    request.write_bytes(data)
    env = dict(os.environ, PYTHONUTF8='1', OMP_NUM_THREADS='4', TOKENIZERS_PARALLELISM='false',
               HF_HOME=str(tool_root() / 'models/huggingface'),
               PADDLE_PDX_CACHE_HOME=os.path.relpath(tool_root() / 'models/paddle', ROOT),
               PADDLE_HOME=os.path.relpath(tool_root() / 'models/paddle', ROOT),
               PADDLE_PDX_MODEL_SOURCE=os.environ.get('PADDLE_PDX_MODEL_SOURCE','bos'),
               HF_HUB_DISABLE_XET='1',
               WORKBENCH_OCR_TOOLS=str(tool_root()))
    command = [str(runtime), '-X', 'utf8', '-m', 'workbench.ocr_worker', '--backend', backend,
               '--input', str(request), '--output', str(response)]
    try:
        with log.open('wb') as handle:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            try:
                process.wait(timeout=1800)
            except subprocess.TimeoutExpired:
                if os.name == 'nt':
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
                else:process.kill()
                process.wait()
                raise RuntimeError('本地解析超过 30 分钟；已有文字保留，请查看日志或拆分文件')
        if process.returncode or not response.is_file():
            detail = log.read_text(encoding='utf-8', errors='replace')[-1400:]
            raise RuntimeError(BACKENDS[backend][1] + f' 未完成（退出码 {process.returncode}）：' + detail)
        return json.loads(response.read_text(encoding='utf-8'))
    finally:
        for temporary in (request,response):
            try:temporary.unlink(missing_ok=True)
            except OSError:pass  # A Windows native crash may temporarily retain its file handle.


def recognize_document(data, cache_dir, backend):
    from pypdf import PdfReader
    version = backend_version(backend)
    digest = hashlib.sha256(data).hexdigest()
    folder = Path(cache_dir) / version / digest
    cache = folder / 'document.json'
    count = len(PdfReader(io.BytesIO(data)).pages)
    if count > 500 or len(data) > 100 * 1024 * 1024:
        raise ValueError('文件超出解析限制（500 页 / 100 MB）')

    def validate(result):
        if (not isinstance(result.get('pages'), list) or
                sorted(p.get('number') for p in result['pages']) != list(range(1, count + 1)) or
                not str(result.get('body_text') or '').strip()):
            raise ValueError('解析器未返回完整分页和可读取正文')
        return result

    try:
        result = validate(json.loads(cache.read_text(encoding='utf-8')))
        if result.get('status') == 'complete' and result.get('version') == version:
            return dict(result, cache_hit=True)
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    result = dict(validate(run_worker(data, folder, backend)), version=version, engine=backend, cache_hit=False)
    if result['status'] != 'complete':
        raise ValueError('部分页面没有正文；已有识别文字已保留，请查看解析日志')
    if backend=='docling_tesseract':
        result=crosscheck_document(data,cache_dir,result)
    folder.mkdir(parents=True, exist_ok=True)
    temporary = cache.with_suffix('.' + uuid.uuid4().hex[:12] + '.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(cache)
    return result


def crosscheck_document(data,cache_dir,result):
    """Flag critical-token disagreements; never synthesize a missing number."""
    from .ocr import recognize_pdf
    baseline=recognize_pdf(data,cache_dir)
    if baseline['status'] not in ('complete','not_needed'):
        result['notes'].append('OCR：独立识别未完整完成，无法进行数字及否定词交叉检查。')
        return result
    blocks=[];sizes={}
    gutter_boxes=[b['bbox'] for p in result['pages'] for b in p.get('excluded_blocks',[])
                  if b.get('reason')=='left_margin_line_number' and b.get('bbox')]
    for page in baseline['pages']:
        layout=next(p for p in result['pages'] if p['number']==page['number'])
        size=layout['page_size'];sizes[page['number']]=size
        if not page.get('lines') or not page.get('image_size'):
            result['notes'].append('OCR：本文件含无逐行坐标的原生文本，保留解析结果，需核对关键数字。')
            return result
        sx=size['width']/page['image_size'][0];sy=size['height']/page['image_size'][1]
        for line in page['lines']:
            if not line.get('box'):continue
            xs,ys=zip(*line['box']);box=[min(xs)*sx,min(ys)*sy,max(xs)*sx,max(ys)*sy]
            x=(box[0]+box[2])/2;y=(box[1]+box[3])/2
            region=next((b for b in layout['blocks'] if b.get('bbox') and
                         b['bbox'][0]<=x<=b['bbox'][2] and b['bbox'][1]<=y<=b['bbox'][3]),{})
            text=line['text'];label='section_header' if text.strip().lower()=='claims' else region.get('label','text')
            excluded=layout.get('excluded_blocks',[])
            furniture=next((b for b in excluded if b.get('bbox') and b.get('reason')!='left_margin_line_number'
                            and b['bbox'][0]-2<=x<=b['bbox'][2]+2 and b['bbox'][1]-2<=y<=b['bbox'][3]+2),None)
            trimmed=None
            if furniture:label='page_header'
            else:
                prefix=re.match(r'^(\d{1,3})(?:\s+|(?=[A-Za-z])|$)',text)
                counter=next((b for b in excluded if b.get('reason')=='left_margin_line_number'
                              and b.get('bbox') and abs(b['bbox'][0]-box[0])<12
                              and abs((b['bbox'][1]+b['bbox'][3])/2-y)<8),None)
                if (counter is None and label!='list_item' and text.strip().isdigit()
                        and any(abs(g[0]-box[0])<12 for g in gutter_boxes)):
                    counter=dict(bbox=box)
                if prefix and counter and 5<=int(prefix[1])<=200 and int(prefix[1])%5==0:
                    text=text[prefix.end():];trimmed=dict(text=prefix[1],bbox=counter['bbox'],reason='left_margin_prefix')
                    if not text:label='page_number'
            block=dict(page=page['number'],text=text,raw_text=line['text'],bbox=box,label=label)
            if trimmed:block['excluded_prefix']=trimmed
            blocks.append(block)
    checked=normalize_layout(blocks,sizes)
    for page in checked['pages']:
        page['excluded_blocks'].extend(b['excluded_prefix'] for b in page['blocks'] if b.get('excluded_prefix'))
    def tokens(text):
        text=text.lower().replace('−','-').replace('≤','<=').replace('≥','>=').replace('≠','!=')
        return Counter(re.findall(r'\b(?:[a-z]{0,3}\d+(?:\.\d+)*[a-z]{0,2}|not|neither|without|never)\b|<=|>=|!=|[<>=±]|(?<!\w)[+-](?=\s*\d)',text))
    first=tokens(result['body_text']);second=tokens(checked['body_text'])
    if first!=second:
        result['parser_ocr_text']=result['text']
        result['parser_body_text']=result['body_text']
        result['crosscheck']=dict(status='disagreement',body_source='rapidocr_with_docling_layout',
            parser_only=dict(first-second),baseline_only=dict(second-first),baseline_version=baseline['version'])
        for original,clean in zip(result['pages'],checked['pages']):
            original['parser_ocr_text']=original['text']
            original['parser_blocks']=original['blocks']
            original.update(clean)
        result['text']=baseline['text'];result['body_text']=checked['body_text']
        result['notes'].append('OCR：两套识别的数字或否定词存在分歧；正文采用现有引擎文字结合 Docling 版面，未拼写或猜补数字；两套读数保留在派生缓存中，请对照原件核对。')
    else:result['crosscheck']=dict(status='checked_token_counts_match',body_source='docling_tesseract',baseline_version=baseline['version'])
    return result
