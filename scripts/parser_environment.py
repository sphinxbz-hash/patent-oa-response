"""Record installed parser/model identities; run with the parser's Python."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('backend',choices=['docling','paddle'])
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]/'workbench-data/tools'
    names=['docling','docling-core','docling-ibm-models','pypdfium2','torch'] if args.backend=='docling' else ['paddleocr','paddlex','paddlepaddle','pypdfium2']
    versions={name:importlib.metadata.version(name) for name in names}
    if args.backend=='docling':
        model=root/'tesseract/tessdata/eng.traineddata'
        versions['tesseract_eng_best_sha256']=hashlib.sha256(model.read_bytes()).hexdigest()
        candidate=root/'tesseract/tesseract.exe'
        if not candidate.is_file():candidate=Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Tesseract-OCR/tesseract.exe'
        command=str(candidate) if candidate.is_file() else shutil.which('tesseract') or 'tesseract'
        versions['tesseract']=subprocess.check_output([command,'--version'],text=True).splitlines()[0]
    destination=root/args.backend/'manifest.json'
    destination.write_text(json.dumps(versions,indent=2),encoding='utf-8')
    print(json.dumps(versions,indent=2))


if __name__=='__main__':main()
