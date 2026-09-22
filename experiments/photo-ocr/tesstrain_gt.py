#!/usr/bin/env python3
"""
tesstrain_gt.py - a tesstrain ground-truth directory from Tesseract-style lines.

Links (symlinks) the real lines of work/tess-lines (build_lines.py --tesseract,
status 'ok') and the synthetic lines of work/tess-synth (synth.py --white) into
one directory, as tesstrain wants: <id>.png + <id>.gt.txt side by side. Real
lines are linked COPIES times (they are few; the synthetic lines would
otherwise dominate). With --holdout A, the lines of the seven photos of half A
are left out, so that a model can be tested on them.

Usage: tesstrain_gt.py [--holdout A] [--copies N] OUTDIR
"""

import argparse
import glob
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HALF_A = {'20251128_143653', '20251128_143901', '20251128_143759', '20251128_143633',
          '20251128_143709', '20251128_143802', '20251128_143813'}

ap = argparse.ArgumentParser()
ap.add_argument('outdir')
ap.add_argument('--holdout', choices=['A'])
ap.add_argument('--copies', type=int, default=4)
a = ap.parse_args()
os.makedirs(a.outdir, exist_ok=True)


def link(src_png, name):
    for ext in ('.png', '.gt.txt'):
        dst = os.path.join(a.outdir, name + ext)
        if not os.path.lexists(dst):
            os.symlink(os.path.abspath(src_png[:-4] + ext), dst)


n_real = n_synth = 0
for row in open(os.path.join(ROOT, 'work', 'tess-lines', 'manifest.tsv'), encoding='utf-8'):
    page, png, _, status = row.split('\t')[:4]
    if status != 'ok' or (a.holdout == 'A' and page in HALF_A):
        continue
    for c in range(a.copies):
        link(png, f'{page}_{os.path.basename(png)[:-4]}_c{c}')
    n_real += 1
for png in sorted(glob.glob(os.path.join(ROOT, 'work', 'tess-synth', 's*.png'))):
    link(png, 'synth_' + os.path.basename(png)[:-4])
    n_synth += 1
print(f'{a.outdir}: {n_real} real lines x {a.copies} + {n_synth} synthetic')
