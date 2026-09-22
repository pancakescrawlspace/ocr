# OCR from tablet photos

How `bin/prep-photo`, `clean-ocr -a` and `bin/ocr-photo` came about. Part 1
starts from one tablet photo of a printed page that Tesseract could not read
as-is: the techniques that were on the table, what the photo really needed,
every experiment with its measured result, and the pipeline that came out of
it. Part 2 takes that pipeline to thirteen more photos and eight scanned
pages, where it fell short, and replaces its line finding with Kraken's; it
also fine-tunes a Kraken recognition model and combines it with Tesseract.
[SESSION-LOG.md](SESSION-LOG.md) has the chronological account, with the
problems met on the way and the commands.

## Contents

Part 1: one photo, Tesseract
- [The photo](#the-photo)
- [Techniques on the table](#techniques-on-the-table)
- [What the photo actually looks like](#what-the-photo-actually-looks-like)
- [How results were measured](#how-results-were-measured)
- [Experiment log](#experiment-log)
- [The prep-photo pipeline](#the-prep-photo-pipeline)
- [The result of part 1](#the-result-of-part-1)

Part 2: fourteen photos, eight scans, and Kraken
- [The material](#the-material)
- [Part 1's pipeline on the new pages](#part-1s-pipeline-on-the-new-pages)
- [Kraken's recognition, off the shelf](#krakens-recognition-off-the-shelf)
- [Kraken's lines, Tesseract's reading](#krakens-lines-tesseracts-reading)
- [Fine-tuning Kraken](#fine-tuning-kraken)
- [Combining the two readings](#combining-the-two-readings)
- [Fine-tuning Tesseract](#fine-tuning-tesseract)
- [The ocr-photo pipeline](#the-ocr-photo-pipeline)
- [Results](#results)
- [A fifteenth photo, and a fix to prep-photo](#a-fifteenth-photo-and-a-fix-to-prep-photo)

Both parts
- [Limitations](#limitations)
- [Ideas for later](#ideas-for-later)
- [Reproducing](#reproducing)

## The photo

`photos/20251128_143633.jpg` (in Git LFS): a tablet photo, 3264×2448 pixels, of a
printed page in a punched plastic sleeve in a ring binder, a red cover behind it.
The page is Dutch liturgical text in a sans-serif typeface: psalm verses in
small print (`L: [10] Voer mijn ziel uit de kerker, …`), stichera in large
print, and `//` before the last line of each sticheron.

Readers have marked the page up for singing:

- dark pen strokes above vowels: grave and acute accents, tildes, short
  dashes, some doubled;
- red underlines below vowels;
- a small pencilled `r` above `schaat` (the print says `schaat`, the reader
  meant `schaart`).

This is ordinary Latin-script print, so Tesseract with the `nld` model is the
right engine. No Kraken model needs to be trained, as long as the image is
cleaned up first.

## Techniques on the table

Before touching the photo, these were the options, roughly from cheapest to
most involved.

**At capture time**, which beats any software fix:
- take the page out of the sleeve;
- use diffuse light and no flash, angled so the reflection misses the lens;
- take two shots with the light from different sides, align them, and keep
  the per-pixel *minimum*. Glare only ever adds light, so this cancels it;
- use cross-polarisation (polariser film on the lamp, a second one on the
  lens at 90°), which removes reflections from plastic entirely;
- use a tablet or phone document-scan mode (Notes/Files "Scan Documents", Microsoft
  Lens, Adobe Scan), which does edge detection, perspective and shading
  correction in one go.

**Geometry:**
- apply the EXIF orientation;
- perspective correction: map four page corners to a rectangle. The corners
  come from contour detection or are clicked by hand, or the geometry is
  derived from the text (the left margin and the baselines);
- dewarp curved pages with page-dewarp (a cubic sheet model fitted to the
  text lines), Leptonica's dewarp, ScanTailor Advanced, or neural models such
  as UVDoc, DocTr and DocRes;
- deskew any residual tilt with a projection profile.

**Light and haze:**
- flat-field correction: estimate the bare paper with a large closing or
  median filter and divide by it;
- denoise before binarising;
- binarise locally rather than globally: Sauvola, Wolf-Jolion (designed for
  low-contrast camera images), Tesseract's own `thresholding_method=2`, or
  neural binarisers such as SBB binarization or Kraken's `nlbin`.

**Handwritten marks:**
- colour separation for red ink;
- connected-component analysis for dark marks: small blobs above the
  x-height band that are not i/j dots or a diaeresis;
- post-OCR cleanup: strip the accents Tesseract invents;
- or keep the marks: train a Kraken model that transcribes them as combining
  characters (U+0300 for a grave, U+0331 for an underline).

**Tesseract vs. Kraken.** Tesseract needs straight, horizontal lines on a
clean background, so all of the above matters. Kraken's neural baseline
segmenter follows skewed and curved lines, so geometry matters much less. But
Kraken needs a recognition model that fits the material, ideally fine-tuned
on a few transcribed pages.

## What the photo actually looks like

Measured before deciding anything:

| Property | Finding | Consequence |
|----------|---------|-------------|
| Orientation | pixels stored landscape with EXIF orientation 6 ("rotate 90°") | Tesseract (via Leptonica) ignores the tag: **empty output** |
| Clipping | 0% of page pixels ≥ 250 | nothing burnt out, so everything is recoverable |
| Brightness | page at 1/5/50/95/99th percentile: 40/81/133/153/166 (of 255); paper brightness per tile ranges 121–172 | grey haze, dim, ~30% falloff toward the right edge |
| Geometry | baselines tilt by up to about half a degree, the left margin by slightly more; the bottom page edge is out of frame, the left edge is under the sleeve strip | mild keystone; page-corner detection would only find the top and right edges |
| Letter size | median ink-blob height 38–39 px; Tesseract estimates 476 dpi from the x-height | resolution is fine |
| Ink colour | warm colour cast; the printed text is R>G>B, e.g. (48,36,24); the dark marks have the same hue | dark marks **cannot** be separated by colour |

## How results were measured

- **Transcription:** `out/20251128_143633/20251128_143633.gt.txt` holds the
  printed text only, without the marks, 1006 characters after normalisation.
  Misprints are kept as printed (`schaat`, `verbied`, `bevrijdt`).
- **Score:** `bin/cer` gives the character error rate, i.e. the Levenshtein
  distance divided by the transcription length. Both texts are normalised
  first: NFC, whitespace runs collapsed, blank lines dropped.
- **Engine:** Tesseract 5.5.3 (Leptonica 1.87.0) with the `nld` "best" model
  and `--psm 4` unless stated otherwise.

## Experiment log

In the order it happened. CER is over the 1006 characters.

| # | Step | CER |
|---|------|-----|
| 1 | photo as is | nothing recognised |
| 2 | EXIF rotation only (baseline) | **5.07%** (51) |
| 3 | flat-field each colour channel; give Tesseract the colour image / the luminance / the red channel | 6.26% / 5.77% / 6.46% |
| 4 | + remove red ink by absorbance ratio, remove marks via density bands in 400 px strips; greyscale / binary output | 3.38% / 3.88% |
| 5 | red ink with hysteresis; 2D density bands | 9.24% |
| 6 | smoothed red test; page mask | 5.27% |
| 7 | bands stretched ±150 px along the line; ink threshold at Otsu +0/30/50/70% | 4.67–6.56% |
| 8 | relative bands (≥ half the local maximum) and the "floats above a line" rule; ink threshold Otsu +0/30/50% | 3.68% / 3.38% / 3.48% |
| 9 | + erase blobs far from any line | 2.49% |
| 10 | + upscale 1.5× (2×: 2.39%) | 2.19% |
| 11 | + clamp faint grey to white, + `tessedit_char_blacklist={}!\|` | 1.79% |
| 12 | rewritten as `bin/prep-photo`; without / with blacklist | 2.29% / 1.89% |
| 13 | + `clean-ocr -a`; without / with blacklist | 1.79% / **1.29%** |

### 1–2. Orientation

With the file as is, Tesseract saw the page lying on its side and produced
nothing. Rotating by the EXIF tag gave 5.07%. The 51 edits fell into three
groups, roughly:

- **about 22 accents** from the marks: `Aanváárd`, `avondgòbéden`, `zònden`,
  `weréld hébt`, `òpgèstàan`, `schaât`, `Gòd`;
- **about 20 from rows of marks merged into the small-print line above
  them**: `vergeving.` became `ie col`, `op de Heer.` became `op de dage`
  plus a line `Ax`, and `[4] Van` became `4 Ve an`;
- **the rest**: `//` read as `Il`, `!!` or `/`; `laat` read as `\aat` and
  `aat`; stray `5` and `-`.

### 3. Flattening the light: worse, not better

Dividing every channel by a paper estimate (block means at 1/8 scale, 7×7
max filter, a speck-removing opening, blur, upscale) made the page evenly
white, yet the error rate went *up*. Dumping Tesseract's own binarised input
(`-c tessedit_write_images=true`) showed why: its binarisation of the
unprocessed photo was already about as clean as that of the flattened one.
Without clipped highlights, uneven light was not what cost characters.

The red channel alone did not remove the red underlines either. The pen is a
dull, dark red, dark in the red channel too.

The flat field stayed in the pipeline anyway. The steps below need a white,
white-balanced page, and photos with stronger light falloff will need it
for OCR too.

### 4. Removing marks and red ink: 3.38%

**Red ink.** After white balancing, work with absorbance, `A = 1 − value`,
which grows with ink coverage. Black ink absorbs red and green light alike;
red ink absorbs far less red than green. The ratio `A_red / A_green` is
independent of how thick the stroke is:

| Pixels | 1st percentile | median |
|--------|----------------|--------|
| printed text, dark core | 0.88 | 0.91 |
| printed text, stroke edges | 0.82 | 0.93 |
| red underlines | — | 0.71–0.81 |

An overlay of `ratio < 0.85` picked out exactly the underlines.

**Marks.** Binarise, label 8-connected components, and find the lines'
x-height bands (the densest rows) in 400 px vertical strips. A blob that
does not touch a band and is not a compact dot is erased.

Result: 3.38% with greyscale output, 3.88% with our own binary output.
Letting Tesseract binarise stayed better throughout. The debug overlay
showed two weak spots:

- strip bands fail where the binder edge adds noise and in sparse strips.
  Three marks above `Sion` are as dense as the four letters of `Sion`;
- the red mask ate into letters (`Hem`, `Hij`): chromatic aberration and
  JPEG chroma subsampling put a coloured fringe on black strokes.

### 5. Hysteresis for red: 9.24%

Strong red pixels as seeds, grown into "weak" red (ratio < 0.9). That weak
threshold lies inside the black-ink distribution (median 0.91–0.93), so the
mask spread from each underline into the letter it touched (`zonden` lost
`zo`). The page border (binder, red cover, dark top), partly whitened, also
produced junk lines.

### 6. Smoothed red test and page mask: 5.27%

- **Red:** Gaussian-smooth the absorbance (σ 1.5 px) before taking the ratio,
  threshold at 0.84, drop red pieces under 15 px, then grow 1 px only into
  pixels with ratio < 0.9. The fringes disappeared and the underlines stayed
  caught.
- **Page:** the largest region whose paper is bright enough; everything else
  becomes white.

The score was still poor, because of the band model.

### 7. Stretched bands: 4.67–6.56%

The debug overlay showed `L` of `L:` and the first `/` of `//` being erased
as marks. Both are isolated tokens, so a density window next to them is half
empty. Stretching the bands ±150 px along the line fixed that but broke
something else: capitals and ascenders (`A`, `dd`) make the zone above the
lowercase letters locally dense enough to count as band, and the stretch
smeared that false band over the marks. A more lenient ink threshold (to
catch faint marks) found *fewer* marks, because more blobs merged.

### 8. Relative bands and positive evidence: 3.38%

Two changes made the line model work:

- **Band** = rows whose ink density (a 301×5 px window) is at least half the
  densest row within ±40 px vertically. That is the lowercase (x-height)
  zone of each line and never the ascender zone. The band is extended ±4 px
  vertically so that baseline punctuation touches it.
- **Mark** = an elongated blob that does not touch a band *and has a band
  just below it* (within ~45 px). Requiring evidence of a line underneath
  keeps isolated tokens such as `L:`, `//` and the `t` of `stem.`.

Ink threshold: Otsu 3.68%, Otsu + 30% of the way to white 3.38%, + 50%
3.48%.

### 9–11. Stray blobs, scale, Tesseract settings: 1.79%

- **Stray blobs:** anything with no band within ~60 px above or below
  (binder rings, the sleeve's top edge, dirt) is erased: 2.49%.
- **Scale:** upscaling 1.5× (letter height 38 → 57 px) gave 2.19%; 2× gave
  2.39%.
- **`--psm 6`:** three times worse on this indented layout (6.2–7.4%).
- **Sauvola** (`-c thresholding_method=2`): no gain once the image is clean
  (2.39% vs 2.49% at 1×, 2.19% for both at 1.5×).
- **Faint grey** lighter than the ink threshold is set to white. Otherwise
  Tesseract still sees faint marks that our component analysis never sees.
- **Blacklist:** `tessedit_char_blacklist={}!|` stops `//` coming out as
  `!!` or `{!`: 1.79% (2.19% without it). This also forbids real `!`.

**Tried and dropped:** telling marks from letters by stroke width. The marks
are nearly as thick as the print once binarised. Median stroke width (twice
the maximum distance transform): marks 10 px, letters ≥ 30 px tall 12 px
(10th percentile 10), small print 10 px.

### 12. `bin/prep-photo`

The experiment was rewritten as a tool, with every size expressed in the
measured letter-height unit `u` so that other resolutions work. The first
version scored 2.88%: the vertical band extension had rounded to 11 px
instead of 9, and marks just above the lowercase zone now touched the band.
With 0.2u it scored 2.29%, or 1.89% with the blacklist.

### 13. `clean-ocr -a`: 1.29%

Marks that touch a letter cannot be separated from it in the image, so they
are handled in the text instead. The `-a` option strips grave, acute,
circumflex and tilde accents, keeps the diaeresis, and leaves `één` and
`vóór` alone. Result: 1.79% without the blacklist, **1.29% with it**.

**Tried last and not adopted:** the marks above `Sion` form a band of their
own. Seen horizontally, diagonal strokes are wide, so the marks row reaches
a density of 0.14–0.15, as dense as a short text line, and the real `Sion`
band (0.52) lies 45 px below, outside the ±1u comparison window.

- Widening the window to ±1.5u removes that false band, but commas at line
  ends then fall outside their own line's band, and the "mark above a line"
  rule erases them.
- A minimum band density of 0.08 or 0.1 changed nothing. 0.12 made the
  blacklist run worse (1.49%) and the run without it better (1.39%).

The total stayed at 1.29% at best, so the parameters were left as they are.

## The prep-photo pipeline

**`bin/prep-photo`**, per photo. `u` is the median height of the ink blobs of
at least 30 px (38 px here).

1. **Orientation:** apply the EXIF tag.
2. **Flat field:** downscale by `f = max(2, round(longest side / 400))`
   (8 here), 7×7 max filter, 7×7 opening against bright specks, Gaussian
   σ 3, upscale. Divide each colour channel by it.
3. **Page:** paper luminance > 0.55 × its 95th percentile; the largest
   4-connected region. Everything outside becomes white.
4. **Red ink:** `A = 1 − flat`, Gaussian σ 1.5. A pixel is red if
   `A_green > 0.12` and `A_red / A_green < 0.84`, in pieces of at least
   15 px, grown by 1 px into pixels with ratio < 0.9. Red pixels become
   white.
5. **Ink:** Otsu on the page, threshold `T = Otsu + 0.3 × (255 − Otsu)`;
   8-connected components.
6. **Line bands:** the density of text-like ink (no specks under u²/120 px,
   nothing taller than 2u; until part 2's fix: nothing wider or taller than
   3u) in a 7.7u × u/8 window. A band is where that
   density is ≥ 0.5 × the maximum within ±u vertically and ≥ 0.06; it is
   extended ±0.1u vertically.
7. **Erase:**
   - specks;
   - blobs with no band within 1.5u above or below them;
   - blobs no taller than 2u (until the fix: no larger than 3u) that do not touch a band, are not a dot
     (aspect ≤ 1.8, filled ≥ 50%), and have a band within 1.15u below.

   Erased pixels, plus a 1 px ring, become white, as does anything lighter
   than `T`.
8. **Upscale:** so that `u` becomes about 58 px (factor rounded to 0.25,
   never below 1), bicubic.
9. **Output:** a greyscale PNG. With `-d`, also an overlay: bands green,
   erased blobs red, red ink blue, off-page darkened.

It takes about 1.3 s for the 8-megapixel photo. Then:

```sh
TESSDATA_PREFIX=tessdata tesseract work/<name>/prep.png - -l nld --psm 4 \
    -c 'tessedit_char_blacklist={}!|' | bin/clean-ocr -a
```

## The result of part 1

CER 1.29% on the first photo (that output has since been replaced by
`bin/ocr-photo`'s, 0.4%). The 13 remaining edits:

| Transcription | OCR | Cause |
|---------------|-----|-------|
| `L:` | `L.` | the faint colon is misread |
| `// dat Gij zijt opgestaan.` | `Il dat Gij zijt Opgestaan.` | `//` misread; the grave mark touching `o` makes it a capital |
| (none) | `_— AA` | marks above `Sion` form a false line band (see step 13) |
| `[4] Van` | `[4] van` | capital lost |
| `bezingen,` | `bezingen, <` | a mark that survived at the line end |

## The material

- **14 tablet photos** (`photos/`), all from the same binder, taken within
  three minutes with a Samsung SM-T220 tablet: two blurred by camera shake
  (143653, 143749), one strongly angled with small print, several with the
  binder's punched holes or a dark hand shadow in the picture, and all with
  the same kind of reader's marks (stress marks, red underlines, a few pencil
  corrections and pasted correction slips). Transcribed:
  `out/<name>/<name>.gt.txt`, 347 lines, 14,318 characters. Only the first
  photo is in the repository (Git LFS); the others are git-ignored to save
  LFS storage, so the transcriptions and outputs of those are committed but
  the photos themselves stay local.
- **8 scanned pages** from `pdf/liturgie.pdf` (pages 16–17 and 21–26; the
  other pages are mostly musical notation): the same kind of pages with the
  same kind of marks, but as sharp 296 dpi scans. The PDF has no text layer.
  Transcribed: `out/liturgie-pNN/liturgie-pNN.gt.txt`, 132 lines, 4,549
  characters. These pages are never trained on, which makes them the fairest
  test of anything trained on the photos.

Transcriptions follow the print, not the reader's corrections (`zonden man`
where a pen changed it to `zonder`), keep misprints (`verbied`, `hour`,
`aallerzuiverst`), and leave out the marks, margin notes and slips.
`experiments/photo-ocr/evalset.py` scores any run against all of them, per
group.

## Part 1's pipeline on the new pages

| Pipeline | Photos | Scans |
|----------|--------|-------|
| `tesseract --psm 4` on the EXIF-rotated image | 11.84% | 9.69% |
| `prep-photo`, `tesseract --psm 4`, `clean-ocr -a` | 6.54% | 2.68% |

Per photo, part 1's pipeline ranged from 1.1% to 25.8%. The failures were
almost all in *finding lines*: Tesseract's page layout analysis merged lines
of different sizes, split lines at binder holes, read shadows and holes as
text, and on the blurred photos lost whole lines of small print.

## Kraken's recognition, off the shelf

Two public Kraken models were tried on the first photo, with Kraken's own
segmentation (`kraken … segment -bl ocr -m MODEL`):

| Model | Rotated photo | `prep.png` |
|-------|---------------|------------|
| McCATMuS (print, handwriting and typescript, 16th–21st century) | 16.7% | 14.8% |
| CATMuS-Print Large | 4.8% | 7.2% |
| (part 1: `prep-photo` + Tesseract) | | 1.3% |

On seven photos CATMuS-Print scored 8.1% against 7.5% for part 1's pipeline:
better on the two blurred photos, worse on all others. Neither model knows
this modern sans-serif well (`Gu` for `Gij`, `rn` for `m`), and neither
ignores the marks. But **Kraken's segmentation found every line** on every
photo, including the blurred and the angled ones.

## Kraken's lines, Tesseract's reading

So the two were combined: Kraken finds and straightens the lines, Tesseract
reads each line on its own (`--psm 7`, a single text line), so that its page
layout analysis is never used. Getting the line images right took several
steps (photos / scans):

| Step | Photos | Scans |
|------|--------|-------|
| Kraken's line images as they come (black outside the line polygon) | 16.3% | |
| white instead of black outside the polygon, from an exact mask | 3.69% | |
| baselines lengthened by 0.4 line heights at both ends, polygons extended under the baseline | 3.27% | 2.42% |
| lines with almost no letters dropped | 3.12% | 1.47% |
| lines read from the image with only the lighting flattened | **2.65%** | **1.47%** |

- **Black borders.** Kraken fills everything outside a line's polygon with
  black. On a faint, blurred line that black dominates Tesseract's threshold
  and the text vanishes (one blurred photo went to 77% CER). The same
  extraction applied to an all-white image gives the exact "outside" mask;
  whitening it plus 2 px (the mask's edge is anti-aliased) fixed it.
- **Cut-off punctuation.** blla ends a baseline at the last letter, and the
  line polygon hugs the letters: a line-final `,` or `.` falls outside the
  image, and the polygon's lower edge clips comma tails into full stops.
  Lengthening the baselines, recomputing the polygons with Kraken's own
  polygonizer, and adding a strip under the baseline (0.35 of the line's own
  height) brought them back. A plain fixed-height band around every baseline
  was worse, because print sizes vary on a page.
- **Junk lines.** Kraken also finds "lines" in page edges, binder holes and
  shadows. Tesseract's word confidence does not separate them from real text
  (dropping lines below 40 already cost real text), but they are all tiny:
  lines with fewer than 3 letters, or fewer than 8 at a confidence below 55,
  are dropped. That removed 30 lines in 22 pages, all junk.
- **Reading from a gentler image.** On blurred photos prep-photo's red-ink
  and mark removal ate into letters where underlines ran into them, and once
  erased a faint word. Lines are still *found* on the cleaned image, where
  the marks are gone, but *read* from the image with only the lighting
  flattened (`prep-photo --flat`): 3.12% → 2.65% on the photos, no change on
  the scans. Reading from an image with the red removed but the marks kept
  gave 2.88%.

This is `bin/ocr-photo`.

## Fine-tuning Kraken

In the akafist project a Kraken model trained on the book's own lines beat
everything else. Here:

**Training lines.** `experiments/photo-ocr/build_lines.py` cuts the lines
exactly as Kraken's recogniser sees them at reading time and pairs each with
its transcription line (Tesseract's reading, similarity ≥ 0.6, each line
used once, lengths must agree). 328 lines are usable; 13 where the reader's
pen changed a letter or a correction slip covers text are left out of
training, because the image no longer shows what the transcription says.
The base model is CATMuS-Print Large, fine-tuned with ketos on the CPU (the
Mac's GPU hung).

**Held-out photos.** The photos were split into two halves of seven, A and
B; a model trained on the lines of one half is scored only on the seven
photos of the other half.

**Real lines only.** Trained on 167 lines of one half, the model reached 99%
on its validation lines but 4.9% on the other seven photos (Tesseract hybrid
at the time: 3.0%), and the model trained on all 328 lines read the sharp
scans at 7.8%: it had learnt blurred photo lines, and confused `rn`/`m`,
`ri`/`n` and `f`/`l` with high confidence. The akafist model had about 50
times more lines.

**Synthetic lines.** `experiments/photo-ocr/synth.py` renders lines of
Psalterion text (same register, not the text of any test page) in the pages'
typeface, Arial, with stress-mark strokes and underlines on random vowels,
at blur levels from sharp to very blurred, grey ink, noise, and Kraken's
black border. With 4,000 of these plus the real lines of one half (four
times over), the model read the scans at 2.4% after one epoch instead of
7.8%. Its best result on its seven unseen photos was 4.3%, on the scans
1.9%; the Tesseract hybrid remains better on its own. The validation score
(30 real photo lines) did not predict the scan score: epoch 2 was better
on the scans than epoch 4.

## Combining the two readings

Tesseract and the fine-tuned Kraken model make different mistakes. Per
line, where the readings differ, the one with more words found in a Dutch
vocabulary wins (score: known words minus half the unknown ones; the
vocabulary is that of the Psalterion text; stress accents are ignored); ties
go to Tesseract, and so do Kraken readings with a mean character confidence
below 80. With the half-A model on its seven unseen photos and on the scans:

| | Unseen photos (7) | Scans |
|-|-------------------|-------|
| Tesseract hybrid (`ocr-photo`) | 2.51% | 1.47% |
| fine-tuned Kraken alone | 4.47% | 2.40% |
| combined (`ocr-photo -m`) | **2.30%** | **1.32%** |

Kraken's reading was kept on 21 of 302 lines.

The production model, `models/liturgie-print.safetensors`, is trained the
same way on the lines of all fourteen photos (298 real lines four times over
plus the 4,000 synthetic ones, 30 real lines for validation, 4 epochs, the
checkpoint with the best validation accuracy: 99.2%). It is git-ignored
(23 MB); the training commands are in SESSION-LOG.md, part 3. Only the scans
can test it: alone it reads them at 1.45%, combined with stock Tesseract
(`ocr-photo -m`) at 1.30%, against 1.47% for Tesseract alone.

A caveat found later: the "vocabulary" is that of the Psalterion *OCR text*,
which contains OCR junk (`ee`, `pe`, `se`, `eee`), so some garbage counts as
known words. The comparison still works because both readings are judged by
the same list, but a cleaner list should do better.

## Fine-tuning Tesseract

(The full description, with every parameter, the commands and the pitfalls,
is in [TESSERACT-FINETUNING.md](TESSERACT-FINETUNING.md).)

Tesseract's model is a container that can be unpacked (`combine_tessdata
-u`): the neural network (3.3 MB, spec
`[1,36,0,1Ct3,3,16Mp3,3Lfys64Lfx96Lrx96Lfx192O1c1]`, itself trained in 2017
on synthetic lines, `synth20170629`), the 151 characters it knows, and three
dictionaries (a 478,341-word Dutch word list, punctuation and number
patterns) that its decoder searches with. The network cannot usefully be
loaded into Kraken: there is no converter, and without the dictionary search
it would be a weaker Tesseract. But Tesseract can be fine-tuned itself, with
`tesstrain`, on the same kind of lines: `build_lines.py --tesseract` cuts them
as `ocr-photo` gives them to Tesseract (from `flat.png`, white around them),
`synth.py --white` renders synthetic ones without Kraken's black border, and
`experiments/photo-ocr/train_tesseract.sh` does the rest (8,000 iterations
from `nld`: 5 to 9 minutes on one core, after 1 to 4 minutes of preparing the
line files).

Two things mattered:

- **The dictionary.** tesstrain builds the new model *without* a dictionary
  unless word lists are supplied. Unpacking `nld`'s dictionaries into word
  lists (`dawg2wordlist`) and building the model with them keeps it.
- **Junk lines.** The fine-tuned model reads a page edge as a long string of
  letters (`Vee ee pe: SE ee een Genee …`), too long for the "few letters"
  junk rule, but at a confidence of 23–33 where every real line is above 48
  (and above 30 with the stock model). `ocr-photo` now also drops lines
  below 30.

Half A's seven unseen photos and the scans, with models trained on half B:

| Tesseract model | Unseen photos (7) | Scans |
|-----------------|-------------------|-------|
| `nld`, stock | 2.51% | 1.47% |
| fine-tuned, without dictionary | 2.12% | 1.19% |
| fine-tuned, with `nld`'s dictionary | **1.85%** | 1.28% |
| … combined with the fine-tuned Kraken model (`-m`) | 1.81% | |

The production model, `nld_lit`, is trained on all fourteen photos with the
dictionary. On the scans, which it has never seen, it reads **0.86%**, against
1.47% for stock `nld`; combining it with the Kraken model no longer helps
(0.88%). It is installed as `tessdata/nld_lit.traineddata` (git-ignored, like
all of `tessdata/`) and used with `bin/ocr-photo -l nld_lit`.

What remains on the scans: capitals after a stress mark (`Was`, `Van`,
`Want`, `Uit`: a pen stroke above a lower-case letter looks like the top of a
capital, and the model has learnt that too well), headings (`toon 7` read as
`toon /`), and letters overwritten in pen (`pet graf`).

## The ocr-photo pipeline

Per image:

1. `bin/prep-photo` writes `work/<name>/prep.png` (steps 1–6 of part 1) and
   `work/<name>/flat.png` (steps 1–3 only: lighting flattened, page masked),
   both at the same scale.
2. Kraken's baseline segmenter (blla, the default model) runs on `prep.png`.
   Every baseline is lengthened by 0.4 median line heights at both ends
   (kept 8 px inside the image, where the polygonizer otherwise fails), the
   line polygons are recomputed, and each polygon is joined with a strip
   below its baseline of 0.35 times its own mean height. Where the
   polygonizer still fails, blla's own line is kept.
3. Each line is cut out of `flat.png` and straightened (Kraken's
   `extract_polygons`); everything outside the polygon, plus 2 px, is made
   white.
4. Tesseract reads each line: `--psm 7 -l nld`, characters `{}!|` excluded,
   in parallel.
5. Lines with fewer than 3 letters, fewer than 8 at a mean word confidence
   below 55, or any line below 30, are dropped.
6. With `-m MODEL`: the Kraken model reads the same lines from `prep.png`
   (as it was trained), and per line the better reading is kept (above).
7. `out/<name>/<name>.txt`, and `<name>.clean.txt` through `clean-ocr -a`;
   `work/<name>/lines.json` with every line's geometry and readings.

About 15 seconds a page on this Mac (10 cores in use), a few more with `-m`.

## Results

With the current code (including the fix of the next section), on all 15
photos (15,015 characters) and the 8 scans:

| Pipeline | Photos (15) | Scans (8) |
|----------|-------------|-----------|
| `tesseract --psm 4`, EXIF-rotated image | 11.85% | 9.69% |
| part 1: `prep-photo` + `tesseract --psm 4` + `clean-ocr -a` | 6.57% | 2.86% |
| `ocr-photo` | 2.46% | 1.49% |
| `ocr-photo -m models/liturgie-print.safetensors` (fine-tuned Kraken) | 2.30%* | 1.32% |
| `ocr-photo -l nld_lit` (fine-tuned Tesseract) | 1.89%* | **0.86%** |
| `ocr-photo -l nld_lit -m …` (both) | | 0.88% |

\* The production models are trained on fourteen of the photos, so on the
photos only the half-A models can be measured, on the seven photos they did
not see (`ocr-photo` scores 2.59% on those seven). On the fifteenth photo,
which no model saw: `ocr-photo` 3.01%, `-l nld_lit` 2.87%, `-m` 2.73%.

The photos' remaining errors are concentrated on the two blurred ones
(143653: 8.0%, 143749: 3.6%, most of it in small print); the other thirteen
are at 1.75% together. The typical remaining errors are
punctuation (`L:` read as `L.`, a final `,` as `.`), capitals after a stress
mark (`Opgestaan`), `//` read as `Il`, and single letters in blurred small
print.

## A fifteenth photo, and a fix to prep-photo

`photos/20260707_215411.jpg` was taken months after the others: a different
page (a feast troparion and kondakion), close up, a bluish cast, soft focus,
one line cut off by the frame, and a handwritten correction after the last
printed word. No model had seen it. Every pipeline lost most of its first
line, the italic heading "Feesttropaar toon 7": only `r toon 7` came out.

**The cause.** prep-photo's mark eraser (step 7 of part 1's pipeline) does
not see letters but *blobs*: groups of dark pixels that touch. It sorts them
into three kinds:

1. **specks**, tiny: erased;
2. **"big" blobs**, meant for page edges, binder rings and shadows: they are
   left out when finding where the text lines are, and erased when no text
   line lies within 1.5 letter heights above or below them;
3. **the rest**, letters and pen marks: where these are dense is a text
   line, and small elongated blobs just above a line (stress marks) are
   erased.

A blob counted as "big" if it was more than **3 letter heights wide or
tall**. On a sharp photo every letter is its own blob. On a blurred one,
neighbouring letters bleed into each other and a whole word becomes one blob:
"Feesttropaar" was a single blob about ten letter heights wide but only one
line tall. By its width it was "big", so it did not count towards its own
line (a line was found only for "toon 7"), and being "big" with no line in
reach, it was erased. Kraken finds lines on the cleaned image, so it never
saw a line there; Tesseract reads from the image in which the word was
intact, but only inside the lines Kraken found.

**The fix.** "Big" is now decided by **height only**: more than 2 letter
heights. Page edges, rings and holes are tall and still count as big; a
merged word is wide but one line high, and now counts as text.

**The same bug, earlier and unnoticed.** On the blurred photo 143749 the
word "vertrouwe" had merged into one blob and been erased; Kraken saw a gap
and split the line in two (`[4] Van de ochtendwaks tot de nacht va` and
`we israël op de Heer`). That was put down to the red-ink removal at the
time (reading from `flat.png` recovered part of it); the real cause was this.
With the fix the line reads `… tot de nacht vertrouwe \sraël op de Heer`.

| | before | after |
|-|--------|-------|
| the fifteenth photo, `ocr-photo` | 4.73% | 3.01% |
| 143749 (blurred, angled), `ocr-photo` | 7.3% | 3.6% |
| all 15 photos, `ocr-photo` | 2.75% | **2.46%** |
| the 8 scans, `ocr-photo` | 1.47% | 1.49% |
| the first photo, part 1's pipeline | 1.29% | 0.70% |

On some sharp photos a few characters got worse (`Gij` read as `Jij`, a `//`
lost, `L:` as `L`): wide, low blobs such as an underline or a row of merged
marks now count as text and move Kraken's line outline slightly. Tesseract
still reads the same pixels; only where the line is cut changes. The
fine-tuned models were trained before the fix, on lines cut with the old
prep-photo; their test scores in "Results" are measured with the fix.

## Limitations

- **One book's print.** Everything was tuned and trained on pages from one
  binder, in Arial with the same kind of marks. Other typefaces need their
  own synthetic lines (`synth.py` takes any font) and, for the Kraken model,
  their own transcribed lines.
- **Blurred photos stay hard.** The worst shaken photo (143653) is at 8%
  even now, most of it in small print; no preprocessing recovers detail that
  is not in the picture. Retake it.
- **Touching marks** stay in the image and come out as accents or capitals
  (`Opgestaan`). `clean-ocr -a` strips the accents but also genuine ones
  (`café`), which is why it is opt-in.
- **Only red** ink is recognised by colour. Pens of other colours count as
  dark marks.
- **No perspective correction or dewarping.** Kraken's lines follow slanted
  and slightly curved text, which covers hand-held photos of flat pages, but
  not a thick book photographed at an angle.
- **Burnt-out glare** cannot be recovered.
- **The blacklist** forbids real `!` and `{`.
- **The lexicon** for combining readings is the Psalterion's vocabulary; a
  text with a different vocabulary needs its own (`--lexicon`).
- **Small test sets**: 14 photos and 8 scans, 18,867 characters. Differences
  of a tenth of a percent are within noise.

## Ideas for later

- **More real training lines.** The Kraken model is trained on 328 real
  lines; akafist's had 16,799. Correcting `ocr-photo` output for more pages
  is now quick, and every corrected page adds about 25 lines.
- **Train on the scans too**, once there are other scans to test on.
- **A clean lexicon** for `-m`: the Psalterion vocabulary filtered through
  `nld`'s word list, or the corrected transcriptions.
- **Stress marks and capitals.** Synthetic lines with marks above *capital*
  letters too might stop the fine-tuned Tesseract from capitalising after a
  mark.
- **Keeping the marks:** if the stress and chant marks are wanted, a
  recognition model trained with the marks transcribed as combining
  characters.
- **Multi-shot glare removal:** a per-pixel minimum of two registered shots
  with the light from different sides.

## Reproducing

Setup (once):

```sh
python3 -m pip install --user numpy Pillow opencv-python-headless
python3 -m venv ~/.venvs/kraken && ~/.venvs/kraken/bin/pip install kraken
bin/fetch-tessdata nld
~/.venvs/kraken/bin/kraken get 10.5281/zenodo.10592716     # CATMuS-Print Large, only for training
```

Part 1, the first photo:

```sh
bin/prep-photo -d photos/20251128_143633.jpg  # -> work/20251128_143633/prep.png, debug.png
TESSDATA_PREFIX=tessdata tesseract work/20251128_143633/prep.png - -l nld --psm 4 \
    -c 'tessedit_char_blacklist={}!|' | bin/clean-ocr -a > /tmp/part1.txt
bin/cer -d out/20251128_143633/20251128_143633.gt.txt /tmp/part1.txt      # 1.29%
```

Part 2, all pages:

```sh
mkdir -p work/liturgie                        # the eight scanned pages as images
for p in 16 17 21 22 23 24 25 26; do
  pdfimages -j -f $p -l $p pdf/liturgie.pdf work/liturgie/tmp && mv work/liturgie/tmp-000.jpg work/liturgie/liturgie-p$p.jpg
done
bin/ocr-photo photos/*.jpg work/liturgie/*.jpg
experiments/photo-ocr/evalset.py              # photos 2.65%, scans 1.47%
bin/ocr-photo -m models/liturgie-print.safetensors work/liturgie/*.jpg   # model: see training below
experiments/photo-ocr/evalset.py              # scans: see Results
```

Training the Kraken model (about 15 minutes an epoch on the CPU):

```sh
~/.venvs/kraken/bin/python experiments/photo-ocr/build_lines.py work/kraken-lines $(ls photos | sed 's/\.jpg$//')
python3 experiments/photo-ocr/synth.py 4000 work/kraken-synth
# training and validation lists, and the ketos and ketos convert commands: SESSION-LOG.md, part 3
# (the model, models/liturgie-print.safetensors, is git-ignored: 23 MB)
```

Fine-tuning Tesseract (setup of the training tools: see the script's header):

```sh
~/.venvs/kraken/bin/python experiments/photo-ocr/build_lines.py --tesseract work/tess-lines $(ls photos | sed 's/\.jpg$//')
python3 experiments/photo-ocr/synth.py --white 4000 work/tess-synth
experiments/photo-ocr/train_tesseract.sh --holdout A nld_lit_A     # half A left out, for testing
experiments/photo-ocr/train_tesseract.sh nld_lit                   # all photos -> tessdata/nld_lit.traineddata
bin/ocr-photo -l nld_lit --out /tmp/nld_lit work/liturgie/*.jpg
experiments/photo-ocr/evalset.py '/tmp/nld_lit/{}.clean.txt'      # scans 0.86%
```

Environment of the measurements: macOS; Python 3.11.6 with numpy 2.4.6,
Pillow 12.3.0 and opencv-python-headless 5.0.0; Tesseract 5.5.3 with
Leptonica 1.87.0 and the `nld` "best" model; Kraken 7.1.1 with torch 2.14
(in `~/.venvs/kraken`), all on the CPU. The ImageMagick `magick` binary
on this machine failed to start (missing `libraw_r.23.dylib`) and was not
used.
