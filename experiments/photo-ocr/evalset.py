#!/usr/bin/env python3
"""
evalset.py - score OCR output for every page that has a hand transcription.

A transcription is out/<name>/<name>.gt.txt. The pages fall into two groups:
the phone photos (20251128_*) and the scanned PDF pages (liturgie-p*), which
are scored and totalled separately.

Usage: experiments/photo-ocr/evalset.py [PATTERN...]
  PATTERN   where a run's output for page <name> is, with {} for the name
            [out/{}/{}.clean.txt]
e.g.  evalset.py 'out/{}/{}.clean.txt' '/tmp/run2/{}.txt'

Uses the same normalisation and edit distance as bin/cer.
"""

import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
cer = {}
exec(compile(open(os.path.join(ROOT, 'bin', 'cer')).read().replace('if __name__ == "__main__":', 'if False:'),
             'cer', 'exec'), cer)

names = sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(ROOT, 'out', '*', '*.gt.txt')))
groups = [('photos', [n for n in names if not n.startswith('liturgie')]),
          ('scans', [n for n in names if n.startswith('liturgie')])]

for pattern in sys.argv[1:] or ['out/{}/{}.clean.txt']:
    print(pattern)
    for gname, members in groups:
        td = tn = 0
        row = []
        for n in members:
            gt = cer['normalise'](open(os.path.join(ROOT, 'out', n, n + '.gt.txt'), encoding='utf-8').read())
            f = pattern.replace('{}', n)
            f = f if os.path.isabs(f) else os.path.join(ROOT, f)
            if not os.path.exists(f):
                row.append(f'{n.split("_")[-1]}: --')
                continue
            d = cer['distance'](gt, cer['normalise'](open(f, encoding='utf-8').read()))
            td += d
            tn += len(gt)
            row.append(f'{n.split("_")[-1].replace("liturgie-", "")}:{100 * d / len(gt):.1f}')
        if tn:
            print(f'  {gname:6s} CER {100 * td / tn:5.2f}% ({td}/{tn})  ' + ' '.join(row))
