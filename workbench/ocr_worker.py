"""Subprocess entry point; imports optional packages only inside their runtime."""
import argparse
import json
from pathlib import Path

from .parsers import normalize_layout, tool_root, tesseract_command


def docling_document(path):
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TesseractCliOcrOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    tess = tool_root() / 'tesseract'
    options = PdfPipelineOptions(do_table_structure=False, do_code_enrichment=False,
        do_formula_enrichment=False,generate_parsed_pages=True)
    options.layout_options.model_spec.revision='8f39ad3c0b4c58e9c2d2c84a38465abf757272d8'
    options.ocr_options = TesseractCliOcrOptions(lang=['eng'], force_full_page_ocr=True,
        tesseract_cmd=tesseract_command(),
        path=str(tess/'tessdata'), psm=3,scale=300/72)
    converter = DocumentConverter(format_options={InputFormat.PDF:PdfFormatOption(
        pipeline_options=options,backend=PyPdfiumDocumentBackend)})
    conversion = converter.convert(path)
    document = conversion.document
    payload = document.export_to_dict()
    result=docling_layout(payload)
    for page in conversion.pages:
        target=next((p for p in result['pages'] if p['number']==page.page_no),None)
        if target is not None and page.cells:
            lines=[]
            for cell in page.cells:
                b=cell.rect.to_bounding_box().to_top_left_origin(page_height=page.size.height)
                lines.append(dict(text=cell.text,bbox=[b.l,b.t,b.r,b.b]))
            supplement_page(target,lines)
    return finish_pages(result)


def docling_layout(payload):
    """Adapt Docling's explicit reading order and original list markers."""
    pages = {int(number):dict(width=page['size']['width'],height=page['size']['height'])
             for number,page in payload['pages'].items()}
    nodes = {node['self_ref']:node for key in ('texts','groups','tables','pictures') for node in payload.get(key,[])}
    ordered, seen = [], set()
    def visit(node):
        ref=node.get('$ref')
        if ref:
            if ref in seen:return
            seen.add(ref);node=nodes.get(ref,{})
        if node.get('text') is not None or node.get('label')=='table':ordered.append(node)
        for child in node.get('children',[]):visit(child)
    visit(payload.get('body',{}));visit(payload.get('furniture',{}))
    for node in payload.get('texts',[]):
        if node['self_ref'] not in seen:visit({'$ref':node['self_ref']})
    blocks=[]
    for item in ordered:
        content=item.get('text') or item.get('orig') or ''
        if item.get('label')=='table':
            content='\n'.join(str(c.get('text') or '') for c in item.get('data',{}).get('table_cells',[]) if c.get('text'))
        marker=str(item.get('marker') or '')
        provenance=item.get('prov',[])
        # Start offsets define successive segments. This also avoids upstream
        # end offsets that still include a stripped list marker or hyphen.
        for index,prov in enumerate(provenance):
            start=prov.get('charspan',[0,len(content)])[0] if index else 0
            end=provenance[index+1].get('charspan',[len(content)])[0] if index+1<len(provenance) else len(content)
            segment=content[start:end].strip()
            if index==0 and item.get('label')=='list_item' and marker and not segment.startswith(marker):
                segment=marker+' '+segment
            number=int(prov['page_no']);b=prov['bbox'];height=pages[number]['height']
            box=[b['l'],height-b['t'],b['r'],height-b['b']] if b.get('coord_origin')=='BOTTOMLEFT' else [b['l'],b['t'],b['r'],b['b']]
            blocks.append(dict(page=number,text=segment,
                label=item['label'],bbox=box,source_ref=item['self_ref']))
    result=normalize_layout(blocks,pages)
    result['engine_document']=payload
    return result


def supplement_page(page,lines):
    """Keep all OCR lines, including text omitted by layout/table detection."""
    blocks=page['blocks']
    assigned=set()
    for block in blocks:
        box=block.get('bbox')
        if not box:continue
        matches=[]
        for index,line in enumerate(lines):
            b=line['bbox'];x=(b[0]+b[2])/2;y=(b[1]+b[3])/2
            if box[0]<=x<=box[2] and box[1]<=y<=box[3]:matches.append(index)
        assigned.update(matches)
        if not str(block.get('text') or '').strip() and matches:
            block['text']='\n'.join(lines[i]['text'] for i in matches)
            block['ocr_fallback']=True
    for index,line in enumerate(lines):
        if index not in assigned and line['text'].strip():
            addition=dict(page=page['number'],text=line['text'],label='text',
                bbox=line['bbox'],ocr_fallback=True,source_ref='unassigned_ocr_line')
            box=line['bbox'];anchor=len(blocks)
            for position,block in enumerate(blocks):
                other=block.get('bbox')
                if other and box[3]<=other[1] and min(box[2],other[2])>max(box[0],other[0]):
                    anchor=position;break
            blocks.insert(anchor,addition)
    normalized=normalize_layout(blocks,{page['number']:page['page_size']})['pages'][0]
    page.update(normalized)
    page['ocr_lines']=lines
    page['text']='\n'.join(line['text'] for line in lines)


def finish_pages(result):
    normalized=normalize_layout([b for p in result['pages'] for b in p['blocks']],
                                {p['number']:p['page_size'] for p in result['pages']})
    for original,clean in zip(result['pages'],normalized['pages']):
        raw=original['text'];lines=original.get('ocr_lines')
        original.update(clean)
        original['text']=raw
        if lines is not None:original['ocr_lines']=lines
    result['text']='\n\n'.join(p['text'] for p in result['pages'])
    result['body_text']='\n\n'.join(p['body_text'] for p in result['pages'])
    result['empty_pages']=[p['number'] for p in result['pages'] if not p['body_text'].strip()]
    result['status']='partial' if result['empty_pages'] else 'complete'
    return result


def paddle_document(path):
    import numpy as np
    import pypdfium2 as pdfium
    from paddleocr import PPStructureV3
    pipeline=PPStructureV3(lang='en',device='cpu',enable_mkldnn=True,cpu_threads=4,use_doc_orientation_classify=False,
        text_recognition_model_name='en_PP-OCRv5_mobile_rec',text_recognition_batch_size=4,
        text_det_limit_type='max',text_det_limit_side_len=1280,
        use_doc_unwarping=False,use_textline_orientation=False,use_table_recognition=False,
        use_formula_recognition=False,use_chart_recognition=False,use_seal_recognition=False,
        use_region_detection=False)
    blocks=[];sizes={};completed=[]
    pdf=pdfium.PdfDocument(path)
    try:
        for index in range(len(pdf)):
            page=pdf[index]
            width,height=page.get_size()
            scale=min(300/72,(20_000_000/max(1,width*height))**.5)
            bitmap=page.render(scale=scale)
            image=bitmap.to_pil().convert('RGB')
            try:
                sizes[index+1]=dict(width=image.width,height=image.height)
                for output in pipeline.predict(np.asarray(image)[:,:,::-1].copy()):
                    payload=output.json
                    if isinstance(payload,str):payload=json.loads(payload)
                    payload=payload.get('res',payload)
                    for item in payload.get('parsing_res_list',[]):
                        blocks.append(dict(page=index+1,text=item.get('block_content',''),
                            label=item.get('block_label','text'),bbox=item.get('block_bbox'),
                            source_ref=str(item.get('block_id',''))))
                    raw=payload.get('overall_ocr_res') or {}
                    lines=[dict(text=text,bbox=box) for text,box in zip(raw.get('rec_texts',[]),raw.get('rec_boxes',[]))]
                    page_result=normalize_layout([b for b in blocks if b['page']==index+1],{index+1:sizes[index+1]})['pages'][0]
                    if lines:supplement_page(page_result,lines)
                    completed.append(page_result)
                print('已完成第',index+1,'页',flush=True)
            finally:image.close();bitmap.close();page.close()
    finally:pdf.close()
    result=normalize_layout(blocks,sizes)
    result['pages']=completed
    return finish_pages(result)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--backend',choices=['docling_tesseract','paddle_structure'],required=True)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.backend=='paddle_structure':
        import faulthandler
        faulthandler.dump_traceback_later(90,repeat=True)
    result=(docling_document if args.backend=='docling_tesseract' else paddle_document)(args.input)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
