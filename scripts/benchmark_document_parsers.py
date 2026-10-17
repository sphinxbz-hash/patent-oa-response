"""Compare local parsers on the same case originals without changing that case."""
import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workbench.analysis import analyze_case
from workbench.claims import parse_claims
from workbench.ocr import recognize_pdf
from workbench.storage import Store


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--case-id',required=True)
    parser.add_argument('--data-dir',type=Path,default=Path('workbench-data'))
    parser.add_argument('--output',type=Path)
    parser.add_argument('--engines',nargs='+',default=['rapidocr','docling_tesseract','paddle_structure'])
    parser.add_argument('--document-ids',nargs='+')
    args=parser.parse_args()
    store=Store(args.data_dir);case=store.get(args.case_id)
    output=args.output or store.root/'parser-evaluation'/datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    output.mkdir(parents=True,exist_ok=True)
    analysis=analyze_case(case)
    ids=args.document_ids or [d['id'] for key,d in analysis['sources'].items() if d and key in ('response','claims')]
    if not args.document_ids:
        cycle=next((c for c in reversed(case.get('cycles',[])) if c.get('response_id') in ids),{})
        if cycle.get('response_oa_id'):ids.append(cycle['response_oa_id'])
    docs=[d for d in case['documents'] if d['id'] in ids and d.get('local_path')]
    rows=[]
    for doc in docs:
        data=(store.case_dir(case['id'])/doc['local_path']).read_bytes()
        for engine in args.engines:
            print(engine,doc['title'],flush=True)
            start=time.perf_counter()
            row=dict(engine=engine,document_id=doc['id'],title=doc['title'],role=doc['role'],sha256=doc['sha256'])
            try:
                result=recognize_pdf(data,store.root/'.ocr-cache',engine=engine,log=lambda text:print(text,flush=True))
                folder=output/engine;folder.mkdir(exist_ok=True)
                (folder/(doc['id']+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                body=result.get('body_text') or result['text']
                (folder/(doc['id']+'-body.txt')).write_text(body,encoding='utf-8')
                (folder/(doc['id']+'-raw.txt')).write_text(result['text'],encoding='utf-8')
                claim_numbers=[]
                if doc['role']=='claims':
                    try:claim_numbers=[c['number'] for c in parse_claims(body)]
                    except ValueError:claim_numbers=['ambiguous']
                row.update(status=result['status'],pages=len(result['pages']),body_characters=len(body),
                    claim_numbers=claim_numbers,excluded_blocks=sum(len(p.get('excluded_blocks',[])) for p in result['pages']),
                    isolated_counter_lines=len(re.findall(r'(?m)^\s*(?:5|10|15|20|25|30)\s*$',body)),
                    law_firm_reference_in_body='42125 PT-EP' in body,
                    cache_hit=result.get('cache_hit',bool(result.get('ocr_pages') and
                        result.get('cached_pages')==len(result['pages']))),version=result['version'])
            except Exception as exc:row.update(status='failed',error=str(exc)[-2000:])
            row['seconds']=round(time.perf_counter()-start,2);rows.append(row)
            (output/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(row,ensure_ascii=False),flush=True)
    lines=['# 英文案卷解析对测','',f'案件：{case["input_number"]}',
           '相同原件，识别结果独立保存，不修改案件。首次耗时可能包含模型下载和初始化。',
           '以下为自动结构检查；没有人工全文转录，不报告整件字错率，不跨引擎比较置信度。','',
           '| 引擎 | 文件 | 结果 | 页数 | 权项编号 | 排除版面块 | 孤立行号候选 | 缓存 | 秒 |',
           '|---|---|---|---:|---|---:|---:|---|---:|']
    for row in rows:
        lines.append('| '+' | '.join(str(row.get(k,'')) for k in ('engine','title','status','pages','claim_numbers','excluded_blocks','isolated_counter_lines','cache_hit','seconds'))+' |')
    lines+=['','## 需对照 PDF 查看','',
            '- 英文长行是否完整，信函是否串栏，页眉和边栏是否误入正文。',
            '- 权项编号与引用、not 等否定词、技术数字、比较符号和引证号是否正确。',
            '- 排除的行号必须有边缘坐标依据，不能把权项号或技术数字批量删除。',
            '- 原文、正文、结构块及排除记录见各引擎子目录 JSON；PDF 仍在案件 originals 目录。']
    (output/'comparison.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('REPORT',output.resolve(),flush=True)


if __name__=='__main__':main()
