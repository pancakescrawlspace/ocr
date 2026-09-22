#!/usr/bin/env python3
"""
build_lines.py - Kraken training lines from transcribed pages.

For every page with a transcription (out/<name>/<name>.gt.txt) and a cleaned
image (work/<name>/prep.png, made by bin/ocr-photo or bin/prep-photo), the
lines are found with bin/ocr-photo's segmenter and cut out as Kraken sees them
at recognition time (black outside the line polygon). Each line is paired with
its transcription line: Tesseract reads the line (on a white background), and
the best-matching transcription line is taken, each used once, similarity
>= 0.6 on letters and digits only, and the lengths must roughly agree
(otherwise the line image holds only part of the text: 'partial').

Lines whose image a pen correction or a pasted slip changes are marked
'excl' (see EXCLUDE) and not used for training; they still count in every
evaluation.

Writes OUTDIR/<name>/NNN.png + NNN.gt.txt (the form `ketos train -f path`
and tesstrain read) and OUTDIR/manifest.tsv: name, image, similarity, status
(ok/excl/partial/unmatched), transcription, Tesseract's reading.

With --tesseract the line images are the ones bin/ocr-photo gives Tesseract
instead: cut from work/<name>/flat.png, white outside the line polygon.

Usage: build_lines.py [--tesseract] OUTDIR [NAME...]   (default: every transcribed page)
Run with Kraken's python: ~/.venvs/kraken/bin/python build_lines.py ...
"""

import difflib
import glob
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from importlib.machinery import SourceFileLoader

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['OCR_PHOTO_REEXEC'] = '1'
op = SourceFileLoader('ocr_photo', os.path.join(ROOT, 'bin', 'ocr-photo')).load_module()
os.environ.setdefault('TESSDATA_PREFIX', os.path.join(ROOT, 'tessdata'))

EXCLUDE = {'20251128_143901': ['De boos van de duivel', 'heb ik U verb mijn ziel'],
           '20251128_143907': ['heb ik U ver, mijn ziel', 'het vleest heeft'],
           '20251128_143709': ['De Heer regeert', 'rechtvardigen', 'opgestaan zijn uit de doden'],
           '20251128_143808': ['De Heer regeert', 'Door het hour hebt'],
           '20251128_143914': ['De Heer regeert'],
           '20251128_143714': ['Wenend haastten', 'vervulling gedaan'],
           '20251128_143813': ['baart zonden man']}


def key(t):
    t = unicodedata.normalize('NFD', t.lower())
    return re.sub(r'[^a-z0-9]', '', ''.join(c for c in t if not unicodedata.combining(c)))


def main():
    args = sys.argv[1:]
    for_tesseract = '--tesseract' in args
    args = [a for a in args if a != '--tesseract']
    outdir = args[0]
    names = args[1:] or sorted(os.path.basename(os.path.dirname(p))
                                   for p in glob.glob(os.path.join(ROOT, 'out', '*', '*.gt.txt')))
    os.makedirs(outdir, exist_ok=True)
    man = open(os.path.join(outdir, 'manifest.tsv'), 'w', encoding='utf-8')
    for name in names:
        prep = os.path.join(ROOT, 'work', name, 'prep.png')
        if not os.path.exists(prep):
            print(f'{name}: no {prep}, skipped', file=sys.stderr)
            continue
        im = Image.open(prep).convert('L')
        flat = Image.open(os.path.join(ROOT, 'work', name, 'flat.png')).convert('L') if for_tesseract else None
        gt = [l.strip() for l in open(os.path.join(ROOT, 'out', name, name + '.gt.txt'), encoding='utf-8') if l.strip()]
        seg = op.segment(im)
        out = os.path.join(outdir, name)
        os.makedirs(out, exist_ok=True)
        lines = []
        with tempfile.TemporaryDirectory() as td:
            train_ims = op.line_images(flat, seg) if for_tesseract else op.line_images(im, seg, white=False)
            for k, (line_im, white) in enumerate(zip(train_ims, op.line_images(im, seg))):
                p = os.path.join(out, f'{k:03d}.png')
                line_im.save(p)
                white.save(os.path.join(td, 'l.png'))
                lines.append((p, op.read_line(os.path.join(td, 'l.png'), 'nld', '{}!|')[0]))
        sims = sorted(((difflib.SequenceMatcher(None, key(t), key(g)).ratio(), i, j)
                       for i, (_, t) in enumerate(lines) for j, g in enumerate(gt) if key(t) and key(g)), reverse=True)
        used_i, used_j, pairs = set(), set(), {}
        for s, i, j in sims:
            if s < 0.6:
                break
            if i not in used_i and j not in used_j:
                used_i.add(i)
                used_j.add(j)
                pairs[i] = (j, s)
        for i, (p, t) in enumerate(lines):
            if i not in pairs:
                man.write(f'{name}\t{p}\t0\tunmatched\t\t{t}\n')
                continue
            j, s = pairs[i]
            ratio = len(key(t)) / max(1, len(key(gt[j])))
            status = ('excl' if any(x in gt[j] for x in EXCLUDE.get(name, [])) else
                      'partial' if not 0.85 <= ratio <= 1.2 else 'ok')
            open(p[:-4] + '.gt.txt', 'w', encoding='utf-8').write(gt[j] + '\n')
            man.write(f'{name}\t{p}\t{s:.2f}\t{status}\t{gt[j]}\t{t}\n')
        print(f'{name}: {len(lines)} lines, {len(pairs)} matched of {len(gt)} transcribed', file=sys.stderr)


if __name__ == '__main__':
    main()
