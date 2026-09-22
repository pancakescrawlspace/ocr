#!/usr/bin/env python3
"""
synth.py - synthetic Kraken training lines in the typeface of the photographed pages.

The pages are set in Arial. Real transcribed lines are few (about 330), and a
model fine-tuned on them alone learns the look of blurred photo lines and fails
on sharp scans (7.8% CER on the PDF pages). Rendered lines add the typeface at
every sharpness: Psalterion text (out/Psalterion/Psalterion.clean.txt, the same
register as the liturgy, and not the text of any test page), sometimes with an
'L: [n] ', '[n] ' or '// ' prefix as on the pages, in Arial (5% italic),
42-80 px, with pen-like strokes above and underlines below random vowels
(which the transcription ignores, so the model learns to ignore them),
slight shear and rotation, Gaussian blur of 0.4-3.5 px, grey ink on light
paper, noise, sometimes the lightest grey clamped to white (as prep-photo
does), and mostly the black fill Kraken puts outside a line polygon.

Writes OUTDIR/sNNNNN.png + .gt.txt and OUTDIR/list.txt.
Usage: synth.py [--white] N OUTDIR   (fixed seeds: the same N gives the same lines)
  --white   no black border: lines as bin/ocr-photo gives them to Tesseract
Needs Pillow, numpy and /System/Library/Fonts/Supplemental/Arial.ttf (macOS).
"""
import os, random, re, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

WHITE = '--white' in sys.argv
N, OUT = [int(a) if a.isdigit() else a for a in sys.argv[1:] if a != '--white']
os.makedirs(OUT, exist_ok=True)
rnd = random.Random(7)
FONTS = '/System/Library/Fonts/Supplemental/'
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
text = [l.strip() for l in open(os.path.join(ROOT, 'out', 'Psalterion', 'Psalterion.clean.txt'), encoding='utf-8')]
text = [re.sub(r'\s*\*$', '', l) for l in text if 12 <= len(l) <= 80 and not l.startswith('===')]
VOWELS = 'aeiouAEIOU'


def sample_text():
    t = rnd.choice(text)
    r = rnd.random()
    if r < 0.12:
        t = f'L: [{rnd.randint(1, 10)}] ' + t
    elif r < 0.22:
        t = f'[{rnd.randint(1, 10)}] ' + t
    elif r < 0.34:
        t = '// ' + t
    if rnd.random() < 0.3:   # also shorter lines, as in the stichera
        w = t.split()
        if len(w) > 4:
            k = rnd.randint(2, len(w) - 1)
            t = ' '.join(w[:k]) if rnd.random() < 0.5 else ' '.join(w[-k:])
    return t


def render(t):
    italic = rnd.random() < 0.05
    size = rnd.randint(42, 80)
    font = ImageFont.truetype(FONTS + ('Arial Italic.ttf' if italic else 'Arial.ttf'), size)
    asc, desc = font.getmetrics()
    w = int(font.getlength(t)) + 2 * size
    h = int((asc + desc) * rnd.uniform(1.25, 1.6))
    x0, top = size, (h - asc - desc) // 2
    im = Image.new('L', (w, h), 0)            # ink mask: 255 = ink
    d = ImageDraw.Draw(im)
    d.text((x0, top), t, font=font, fill=255)
    base = top + asc
    xh = size * 0.52                            # x-height of Arial
    stroke = max(2, int(size * 0.08))
    p_mark = rnd.choice([0, 0.15, 0.35, 0.5])
    for k, c in enumerate(t):
        if c not in VOWELS or rnd.random() > p_mark:
            continue
        a, b = font.getlength(t[:k]), font.getlength(t[:k + 1])
        cx = x0 + (a + b) / 2 + rnd.uniform(-3, 3)
        kind = rnd.random()
        if kind < 0.55:                         # accent-like stroke above the letter
            y = base - xh - rnd.uniform(0.15, 0.5) * xh
            L = rnd.uniform(0.25, 0.45) * xh
            s = rnd.choice([-1, 1])
            d.line([(cx - s * L / 3, y), (cx + s * L / 3, y - L)], fill=255, width=stroke)
            if rnd.random() < 0.2:
                d.line([(cx - L, y - L / 2), (cx - L / 3, y - L / 2)], fill=255, width=stroke)
        else:                                   # underline below the letter
            y = base + rnd.uniform(0.08, 0.3) * size
            half = (b - a) * rnd.uniform(0.4, 0.7)
            d.line([(cx - half, y), (cx + half, y + rnd.uniform(-2, 2))], fill=255, width=max(2, stroke - 1))
    if italic is False and rnd.random() < 0.5:
        im = im.transform(im.size, Image.AFFINE, (1, rnd.uniform(-0.04, 0.04), 0, 0, 1, 0), Image.BILINEAR)
    im = im.rotate(rnd.uniform(-0.6, 0.6), resample=Image.BILINEAR, fillcolor=0)
    return im, h


def degrade(mask, h):
    m = np.asarray(mask.filter(ImageFilter.GaussianBlur(rnd.choice([0.4, 0.8, 1.2, 1.8, 2.6, 3.5])))) / 255.0
    ink = rnd.uniform(0, 120)
    paper = rnd.uniform(215, 255)
    a = paper - (paper - ink) * m
    a += np.random.default_rng(rnd.randrange(1 << 30)).normal(0, rnd.uniform(0, 8), a.shape)
    if rnd.random() < 0.5:                      # prep-photo clamps the lightest grey to white
        a = np.where(a > rnd.uniform(200, 235), 255, a)
    a = a.clip(0, 255)
    if rnd.random() < 0.7 and not WHITE:        # black fill outside a wavy line polygon, as Kraken extracts lines
        W = a.shape[1]
        xs = np.arange(W)
        for edge in ('top', 'bottom'):
            base = rnd.uniform(0.0, 0.12) * h
            wave = base + rnd.uniform(0, 0.08) * h * np.sin(xs / rnd.uniform(40, 200) + rnd.uniform(0, 6))
            wave = wave.clip(0, None).astype(int)
            for x in range(W):
                if edge == 'top':
                    a[:wave[x], x] = 0
                else:
                    a[a.shape[0] - wave[x]:, x] = 0
    return Image.fromarray(a.astype(np.uint8))


names = []
for i in range(N):
    t = sample_text()
    mask, h = render(t)
    im = degrade(mask, h)
    p = os.path.join(OUT, f's{i:05d}.png')
    im.save(p)
    open(p[:-4] + '.gt.txt', 'w', encoding='utf-8').write(t + '\n')
    names.append(p)
open(os.path.join(OUT, 'list.txt'), 'w').write('\n'.join(names) + '\n')
print(N, 'lines written to', OUT)
