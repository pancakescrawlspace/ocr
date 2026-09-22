#!/usr/bin/env python3
"""
kraken_read.py - read pages with a Kraken recognition model, on bin/ocr-photo's lines.

The lines come from bin/ocr-photo's segmenter (lengthened baselines, polygons
reaching under the baseline), so a Kraken model and Tesseract are compared on
exactly the same line images. Per page, OUTDIR/<name>.tsv holds the mean
character confidence (0-100) and the text of each line, and OUTDIR/<name>.txt
the lines with confidence >= 80 (lower ones are page edges and binder holes),
through clean-ocr -a.

Usage: kraken_read.py MODEL OUTDIR NAME...
  NAME   a page name (reads work/<name>/prep.png) or an image path
Run with Kraken's python: ~/.venvs/kraken/bin/python kraken_read.py ...

Inference runs on the CPU: Kraken 7's default (device 'auto', i.e. the Mac's
GPU, with worker processes) hung without using any CPU on this machine.
"""

import os
import subprocess
import sys
from importlib.machinery import SourceFileLoader

from PIL import Image
from kraken.configs import RecognitionInferenceConfig
from kraken.tasks import RecognitionTaskModel

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['OCR_PHOTO_REEXEC'] = '1'
op = SourceFileLoader('ocr_photo', os.path.join(ROOT, 'bin', 'ocr-photo')).load_module()

model, outdir, names = sys.argv[1], sys.argv[2], sys.argv[3:]
os.makedirs(outdir, exist_ok=True)
net = RecognitionTaskModel.load_model(model)
cfg = RecognitionInferenceConfig(accelerator='cpu', device=1, num_line_workers=0, num_threads=4)
for name in names:
    if os.path.exists(name):
        path, name = name, os.path.splitext(os.path.basename(name))[0]
    else:
        path = os.path.join(ROOT, 'work', name, 'prep.png')
    im = Image.open(path).convert('L')
    rows = []
    for rec in net.predict(im, op.segment(im), cfg):
        c = rec.confidences
        rows.append((100 * sum(c) / len(c) if c else 0, rec.prediction.strip()))
    with open(os.path.join(outdir, name + '.tsv'), 'w', encoding='utf-8') as f:
        f.writelines(f'{c:.0f}\t{t}\n' for c, t in rows)
    kept = '\n'.join(t for c, t in rows if c >= 80) + '\n'
    clean = subprocess.run([os.path.join(ROOT, 'bin', 'clean-ocr'), '-a'], input=kept, capture_output=True, text=True).stdout
    open(os.path.join(outdir, name + '.txt'), 'w', encoding='utf-8').write(clean)
    print(name, 'done', file=sys.stderr)
