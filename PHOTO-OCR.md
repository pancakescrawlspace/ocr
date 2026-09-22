# OCR from a phone photo

How `bin/prep-photo` and `clean-ocr -a` came about: a phone photo of a printed
page that Tesseract could not read as-is, the techniques that were on the
table, what the photo really needed, every experiment with its measured
result, the final pipeline, and what is still wrong with it.

## Contents

- [The photo](#the-photo)
- [Techniques on the table](#techniques-on-the-table)
- [What the photo actually looks like](#what-the-photo-actually-looks-like)
- [How results were measured](#how-results-were-measured)
- [Experiment log](#experiment-log)
- [The final pipeline](#the-final-pipeline)
- [The result](#the-result)
- [Limitations](#limitations)
- [Ideas for later](#ideas-for-later)
- [Reproducing](#reproducing)

## The photo

`photos/20251128_143633.jpg` (in Git LFS): a phone photo, 3264×2448 pixels, of a
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
- use a phone document-scan mode (Notes/Files "Scan Documents", Microsoft
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

## The final pipeline

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
   nothing larger than 3u) in a 7.7u × u/8 window. A band is where that
   density is ≥ 0.5 × the maximum within ±u vertically and ≥ 0.06; it is
   extended ±0.1u vertically.
7. **Erase:**
   - specks;
   - blobs with no band within 1.5u above or below them;
   - blobs that are not larger than 3u, do not touch a band, are not a dot
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

## The result

`out/20251128_143633/20251128_143633.clean.txt`, CER 1.29%. The 13 remaining
edits:

| Transcription | OCR | Cause |
|---------------|-----|-------|
| `L:` | `L.` | the faint colon is misread |
| `// dat Gij zijt opgestaan.` | `Il dat Gij zijt Opgestaan.` | `//` misread; the grave mark touching `o` makes it a capital |
| (none) | `_— AA` | marks above `Sion` form a false line band (see step 13) |
| `[4] Van` | `[4] van` | capital lost |
| `bezingen,` | `bezingen, <` | a mark that survived at the line end |

## Limitations

- **One photo.** All parameters were tuned on a single photo, so expect to
  adjust them on the next ones. `bin/cer` and a transcription make that
  quick.
- **The line model is density-based.** It works for full lines and is
  fragile where a line is short and has marks nearby. It has no notion of
  baselines.
- **Touching marks** stay in the image. `clean-ocr -a` then also strips
  genuine accents (`café`), which is why it is opt-in.
- **Only red** ink is recognised by colour. Pens of other colours count as
  dark marks.
- **No perspective correction or dewarping.** Fine for a hand-held shot of a
  flat page, not for a book photographed at an angle.
- **Burnt-out glare** cannot be recovered.
- **The blacklist** forbids real `!` and `{`.

## Ideas for later

- **Baselines from Kraken:** take the line positions from Kraken's baseline
  segmenter (`kraken … segment -bl`, available in `~/.venvs/kraken`) instead
  of ink density, and derive the x-height band from the ink relative to each
  baseline. That removes both known failure modes.
- **Perspective correction** from the text itself (baselines and left
  margin), for photos taken at an angle.
- **Multi-shot glare removal:** a per-pixel minimum of two registered shots
  with the light from different sides.
- **Keeping the marks:** if the stress and chant marks are wanted, a Kraken
  recognition model trained with the marks transcribed as combining
  characters.
- **More test photos with transcriptions**, to tune against more than one
  page.

## Reproducing

```sh
python3 -m pip install --user numpy Pillow opencv-python-headless
bin/fetch-tessdata nld                        # if tessdata/nld.traineddata is missing
bin/prep-photo -d photos/20251128_143633.jpg  # -> work/20251128_143633/prep.png, debug.png
TESSDATA_PREFIX=tessdata tesseract work/20251128_143633/prep.png - -l nld --psm 4 \
    -c 'tessedit_char_blacklist={}!|' > out/20251128_143633/20251128_143633.txt
bin/clean-ocr -a out/20251128_143633/20251128_143633.txt > out/20251128_143633/20251128_143633.clean.txt
bin/cer -d out/20251128_143633/20251128_143633.gt.txt out/20251128_143633/*.clean.txt
```

Environment of the measurements: macOS; Python 3.11.6 with numpy 2.4.6,
Pillow 12.3.0 and opencv-python-headless 5.0.0; Tesseract 5.5.3 with
Leptonica 1.87.0 and the `nld` "best" model. The ImageMagick `magick` binary
on this machine failed to start (missing `libraw_r.23.dylib`) and was not
used.
