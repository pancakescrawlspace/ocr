# ocr

A small, reusable toolchain for turning scanned PDFs (and photos of
pages) into plain text with
[Tesseract](https://github.com/tesseract-ocr/tesseract). It was built to OCR
`Psalterion.pdf` (the 1970/1983 Dutch Orthodox psalter, 346 scanned pages) and
is written so that the next document is a one-liner.

```sh
bin/ocr-pdf -l nld -C -m '=== page %d ===' ~/dev/orthodoxy/Psalterion.pdf
# -> out/Psalterion/Psalterion.txt        raw OCR text, one page after another
#    out/Psalterion/Psalterion.clean.txt  same, with common OCR junk stripped
```

For photos of pages, taken with a tablet, phone or camera (and scans without
a text layer), there is a second entry point:

```sh
bin/ocr-photo photos/*.jpg
# -> out/<name>/<name>.txt and <name>.clean.txt per photo
```

Everything is plain shell + Python 3 standard library on top of tools that
MacPorts (or Homebrew/apt) provide. No virtualenv, no `sudo` for language data.
The exceptions are the photo tools: `prep-photo` needs numpy, Pillow and
OpenCV (`pip install --user`), and `ocr-photo` needs Kraken.

## Contents

- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
- [The tools](#the-tools)
  - [`bin/ocr-pdf`](#binocr-pdf)
  - [`bin/ocr-photo`](#binocr-photo)
  - [`bin/prep-photo`](#binprep-photo)
  - [`bin/hocr-text`](#binhocr-text)
  - [`bin/clean-ocr`](#binclean-ocr)
  - [`bin/fetch-tessdata`](#binfetch-tessdata)
- [How the pipeline works](#how-the-pipeline-works)
- [Directory layout](#directory-layout)
- [Tuning and troubleshooting](#tuning-and-troubleshooting)
- [Proofreading the result](#proofreading-the-result)
- [The Psalterion run](#the-psalterion-run)

## Prerequisites

| Tool | Used for | MacPorts | Homebrew |
|------|----------|----------|----------|
| `tesseract` (5.x) | the OCR engine | `port install tesseract` | `brew install tesseract` |
| `pdftoppm`, `pdfinfo`, `pdfunite` (poppler) | rendering pages, page count, joining PDFs | `port install poppler` | `brew install poppler` |
| `python3` | `clean-ocr` (stdlib only) | ships with Xcode CLT | — |
| `curl` | downloading language models | ships with macOS | — |
| `magick` (ImageMagick 7), optional | `-P` image preprocessing | `port install ImageMagick` | `brew install imagemagick` |
| `numpy`, `Pillow`, `opencv-python-headless` | `prep-photo` only | `python3 -m pip install --user numpy Pillow opencv-python-headless` | same |
| Kraken (7.x) | `ocr-photo` only: line finding, optional recognition | `python3 -m venv ~/.venvs/kraken && ~/.venvs/kraken/bin/pip install kraken` | same |

Both scripts run under the stock macOS `/bin/bash` 3.2 as well as newer bash.

**Language data is not part of the `tesseract` package.** `bin/ocr-pdf`
downloads what it needs into `./tessdata/` on first use (see
[`fetch-tessdata`](#binfetch-tessdata)), so there is nothing else to install.
If you would rather use system-wide models (`port install tesseract-nld`,
`brew install tesseract-lang`), point `TESSDATA_DIR` at that directory.

## Quick start

```sh
git clone <this repo> ocr && cd ocr

# Dutch document, all pages, defaults (300 dpi, automatic layout):
bin/ocr-pdf -l nld some-scan.pdf

# Same, plus visible page markers and the cleaned variant:
bin/ocr-pdf -l nld -C -m '=== page %d ===' some-scan.pdf

# Mixed Dutch/Greek text, only pages 10-20, also make a searchable PDF:
bin/ocr-pdf -l nld+ell -f 10 -t 20 -s -q 85 some-scan.pdf
```

Output lands in `out/<basename>/`. Re-running the same command is instant:
every page image and every page's OCR result is cached in `work/<basename>/`
and only missing pages are (re)done. Change a setting that affects the
result (`-r`, `-l`, `-p`, `-P`, `-q`, `-c`) and the affected cache is rebuilt
automatically; use `-F` to force a rebuild.

## The tools

### `bin/ocr-pdf`

The driver. `bin/ocr-pdf -h` prints the full option list:

```
Usage: ocr-pdf [options] FILE.pdf

  -l LANG     Tesseract language(s), '+'-separated for mixed text   [eng]
              Missing models are downloaded with fetch-tessdata.
  -r DPI      render resolution                                     [300]
  -p PSM      Tesseract page segmentation mode (3 = auto layout,
              4 = single column, 6 = single uniform block)          [3]
  -f N        first page                                            [1]
  -t N        last page                                             [last]
  -j N        parallel jobs                                         [CPU count]
  -o DIR      output directory                          [out/<basename>]
  -w DIR      work (cache) directory                    [work/<basename>]
  -m FMT      visible page marker written before each page, printf
              style with %d = page number, e.g. '=== page %d ==='.
              Default: none; pages are separated by a form feed (\f)
              like pdftotext does.
  -P ARGS     ImageMagick operations applied to each rendered page
              before OCR, e.g. '-threshold 60% -morphology Open Square:1'
  -q N        render pages as JPEG at quality N instead of lossless PNG.
              Use with -s: Tesseract embeds the page image as-is, so
              JPEG pages give a searchable PDF a fraction of the size.
  -c KEY=VAL  extra Tesseract config variable (repeatable)
  -s          also produce a searchable PDF (image + invisible text layer)
  -C          also write <basename>.clean.txt, run through clean-ocr
  -T          keep Tesseract's own blank lines instead of placing them
              by line spacing (hocr-text)
  -F          force: discard cached renders and OCR results first
  -h          this help

Environment:
  TESSDATA_DIR  where language models live            [<repo>/tessdata]
```

Language codes are Tesseract's three-letter codes: `nld` Dutch, `eng`
English, `deu` German, `fra` French, `ell` modern Greek, `grc` ancient Greek,
`chu` Church Slavonic, `rus` Russian, `lat` Latin, … (full list in the
[tessdata_best](https://github.com/tesseract-ocr/tessdata_best) repository).
Combine with `+` for documents that mix scripts, but note that every extra
language slows OCR down and slightly raises the error rate for the primary
one, so only add what is really on the page.

### `bin/ocr-photo`

OCR for photos of printed pages (tablet, phone, camera), and for page scans
without a text layer. It combines three things:

1. `bin/prep-photo` (below) cleans the photo: rotation, lighting, red ink,
   pen marks, the surroundings of the page;
2. Kraken's neural baseline segmenter finds the text lines on the cleaned
   image, even where the page is blurred, curved or photographed at an angle.
   Each baseline is lengthened a little at both ends and each line reaches a
   little below its baseline, so that final commas and full stops, which
   Kraken cuts off, are kept;
3. Tesseract reads each line on its own (`--psm 7`), cut out of the image
   with only the lighting flattened (the mark eraser sometimes eats into
   letters on blurred photos), with white around it.

Lines with almost no letters or a very low confidence (page edges, binder
holes) are dropped, and the result goes through `clean-ocr -a`.

```sh
bin/ocr-photo photos/*.jpg                  # -> out/<name>/<name>.txt, .clean.txt
bin/ocr-photo -d photo.jpg                  # also work/<name>/lines.png: the lines found
bin/ocr-photo -l nld_lit photo.jpg          # with the fine-tuned Tesseract model (best)
bin/ocr-photo -m models/liturgie-print.safetensors photo.jpg   # also read with a Kraken model
bin/ocr-photo --out /tmp/try photo.jpg      # results elsewhere than out/<name>/
# (the fine-tuned models are not in the repository; PHOTO-OCR.md, "Reproducing", trains them)
```

| Option | Meaning |
|--------|---------|
| `-l LANG` | Tesseract language [`nld`] |
| `-b CHARS` | characters Tesseract may not output [`{}!\|`]; `!` because `//` is otherwise read as `!!` |
| `-j N` | Tesseract processes in parallel [CPU count] |
| `-m MODEL` | also read every line with this Kraken recognition model, and keep per line the reading with more words found in the lexicon |
| `--lexicon FILE` | text whose words count as known [`out/Psalterion/Psalterion.clean.txt`] |
| `-d` | also write `work/<name>/lines.png` (line polygons green, dropped lines red, baselines blue) |
| `--no-prep` | skip prep-photo: segment and read the image as it is |
| `--keep-accents` | `clean-ocr` without `-a` |
| `--out DIR` | write `<DIR>/<name>.txt` and `.clean.txt` instead of `out/<name>/` |

`work/<name>/lines.json` keeps, per line, the baseline, the polygon, both
readings with their confidences, and which was kept.

It needs Kraken; if `import kraken` fails, the script re-runs itself under
`~/.venvs/kraken/bin/python` (or `$KRAKEN_PYTHON`). Kraken's segmentation
takes a few seconds a page on the CPU, Tesseract about a second a line
(in parallel).

Character error rates on 15 tablet photos and 8 scanned PDF pages, all with
reader's pen marks (15,015 and 4,549 characters, `experiments/photo-ocr/evalset.py`):

| Pipeline | Photos | Scans |
|----------|--------|-------|
| `tesseract --psm 4` on the EXIF-rotated image | 11.9% | 9.7% |
| `prep-photo`, then `tesseract --psm 4`, `clean-ocr -a` | 6.6% | 2.9% |
| `ocr-photo` | 2.46% | 1.49% |
| `ocr-photo -m models/liturgie-print.safetensors` (fine-tuned Kraken, combined) | 2.30%* | 1.32% |
| `ocr-photo -l nld_lit` (fine-tuned Tesseract) | 1.89%* | **0.86%** |

\* measured with models trained on half of the photos, on the seven photos
they did not see (`ocr-photo` scores 2.59% on those). The fine-tuned models
are not in the repository (they are large); `experiments/photo-ocr/`
rebuilds them.

The fine-tuned Tesseract model is the best option found; how it is made, with
every parameter and pitfall, is in [TESSERACT-FINETUNING.md](TESSERACT-FINETUNING.md).
How all of this came about, including every dead end, is in
[PHOTO-OCR.md](PHOTO-OCR.md) and [SESSION-LOG.md](SESSION-LOG.md).

### `bin/prep-photo`

Cleans up a photo of a printed page (tablet, phone, camera) so that
Tesseract can read it. A photo differs from a scan in ways Tesseract does not
handle by itself: the
camera stores the picture sideways with an EXIF "rotate" tag that Tesseract
ignores (it recognises *nothing* in such a file), the light is uneven and a
plastic sleeve adds a grey haze, the binder or table around the page turns
into junk lines, and readers' pen marks come out as letters or accents. The
script, per photo:

1. applies the EXIF orientation;
2. divides each colour channel by an estimate of the bare paper, which makes
   the page evenly white and white-balances it;
3. blanks everything outside the page (the largest bright region);
4. removes red ink: after white balancing, black ink absorbs red and green
   light alike, red ink far less red than green;
5. removes pen marks above the lines: it finds the x-height band of every
   text line from the ink density and erases small, elongated blobs that
   float just above a band without touching it (i/j dots and the dots of ë
   are compact and stay). Blobs nowhere near a line (page edges, binder
   rings, specks) go too. A blob taller than two letter heights is not
   text; a wide but low one is (on blurred photos whole words run together
   into one blob, which must not be taken for a page edge);
6. upscales so that letters are about 58 px tall.

All sizes are relative to the measured letter height. Output is a greyscale
PNG; Tesseract binarises it itself.

```sh
bin/prep-photo -d photo.jpg              # -> work/photo/prep.png, work/photo/debug.png
TESSDATA_PREFIX=tessdata tesseract work/photo/prep.png - -l nld --psm 4 \
    -c 'tessedit_char_blacklist={}!|' | bin/clean-ocr -a > photo.txt
```

| Option | Meaning |
|--------|---------|
| `-o FILE` | output file (only with a single photo) |
| `-s SCALE` | upscale factor instead of the automatic one |
| `-d` | also write `debug.png`: found line bands in green, erased marks and blobs in red, erased red ink in blue. Look at it when a result is off. |
| `--keep-red`, `--keep-marks` | skip step 4 or step 5 |
| `--flat FILE` | also write the image after steps 1–3 only (lighting flattened, page masked), at the same scale; `ocr-photo` reads lines from it |

On its own, measured on the first photo of a page of Dutch liturgical text in a sleeve, with
handwritten stress marks above and red underlines below many vowels
(character error rate against a hand transcription, 1006 characters):

| Pipeline | CER |
|----------|-----|
| the photo as is | nothing recognised (sideways) |
| EXIF-rotated only | 5.1% |
| `prep-photo` | 2.3% |
| … + `tessedit_char_blacklist={}!\|` | 1.9% |
| … + `clean-ocr -a` | 1.3% |

What was learnt on the way:

- Flattening the light alone did not help this photo: as long as nothing is
  burnt out to pure white, Tesseract's own binarisation copes with uneven
  light. The pen marks were what cost characters. Tesseract merges a row of
  marks with the line above it (`vergeving.` became `ie col`) or reads them
  as accents.
- Marks that touch a letter cannot be separated from it (they are as dark
  and nearly as thick as the print) and come out as accents: `Hèer`,
  `zònden`. `clean-ocr -a` strips those again.
- `--psm 4` (one column, mixed sizes); `--psm 6` was three times worse here.
- The blacklist stops the half-verse marker `//` from being read as `!!` or
  `{!`; it still becomes `Il` now and then. Leave the blacklist out for texts
  that contain real `!`.
- Burnt-out glare cannot be recovered afterwards: retake the photo with the
  light at an angle, or take the page out of the sleeve.
- There is no perspective correction: the slight keystone of a hand-held
  photo is well within what Tesseract tolerates. For strongly angled shots,
  use the tablet's or phone's document-scan mode first.

`bin/cer TRANSCRIPTION OCR.txt…` scores OCR output against a hand
transcription (character error rate; `-d` also shows the differing lines).
It is how the numbers above were measured. The full account of how the
pipeline came about, with every experiment and its result, is in
[PHOTO-OCR.md](PHOTO-OCR.md).

### `bin/hocr-text`

Rebuilds a page's text from Tesseract's hOCR output, deciding where the
blank lines go from the line positions instead of from Tesseract's
paragraph detection. `ocr-pdf` runs it on every page unless you pass `-T`.

Tesseract's plain-text output puts a blank line between "paragraphs", but
its paragraph finder is unreliable on verse: in the Psalterion it put a
blank line inside 542 verses (between the `*` half and the rest) and left
out dozens of stanza breaks. The page geometry, on the other hand, is
unambiguous: consecutive lines of a verse have their baselines ~80 px apart
at 300 dpi, and a new stanza starts ~120 px down.

For each pair of consecutive lines it measures the distance between the
baselines, taken at a common x so a slightly rotated page does not skew it.
Where Tesseract's baseline fit is clearly off (a slope unlike the rest of
the page, or a baseline outside its own box, which descenders and specks of
dust sometimes cause), it takes the median of the top-edge, baseline and
bottom-edge distances instead. The page's normal line pitch is the 30th
percentile of these distances, and every distance above 1.25 × pitch gets a
blank line. So does a jump back up the page (a new column). Pages with too
few lines, or whose lines Tesseract broke into fragments (a badly degraded
scan), use the median pitch of the whole document. Words and line breaks
are exactly Tesseract's; only the blank lines change.

```sh
bin/hocr-text work/Doc/ocr/page-0040.hocr               # one page to stdout
bin/hocr-text -o /tmp/text work/Doc/ocr/page-*.hocr     # all pages, one .txt each
bin/hocr-text -d work/Doc/ocr/page-0040.hocr            # show each gap and the verdict
bin/hocr-text -g 1.4 ...                                # break only on larger gaps
```

`-d` is the tool to reach for when a blank line is wrong: it prints the
page's pitch and every line with its distance to the previous one.

### `bin/clean-ocr`

A filter that strips the most common Tesseract artifacts from a text file.
Scanned books produce a small, very regular set of junk — page-edge shadows
and marginal rules read as a lone `|`, `_` or quote mark at the start or end
of a line, dust read as a line of pure punctuation. Each rule targets a
pattern that does not occur in ordinary running text:

1. drop lines with no letter or digit at all (`'`, `_`, `— |.` …);
2. strip a leading stray mark *followed by a space* (`_ Verhef U` →
   `Verhef U`); the mark must be one of `_ ‚ | ' ‘ . , ; : !`, so quotes
   attached to a word (`'t`, `”Hij`) are untouched;
3. strip a trailing ` |` or ` _`;
4. re-attach a stranded `*` line to the end of the previous line (half-verse
   markers in psalters and hymnals, footnote markers elsewhere);
5. strip trailing whitespace and collapse runs of blank lines to one;
6. only with `-a`: strip grave, acute, circumflex and tilde accents, keeping
   the diaeresis (`ë`, `ï`). Meant for pages with handwritten stress or
   chant marks, which Tesseract reads as accents (`Hèer`, `zònden`). `één`
   and `vóór` are left alone; other genuinely accented words (`café`) lose
   their accent, which is why this rule is opt-in.

```sh
bin/clean-ocr out/Doc/Doc.txt > out/Doc/Doc.clean.txt   # clean
bin/clean-ocr -s out/Doc/Doc.txt | less                  # preview as a diff
bin/clean-ocr -a photo.txt                               # also strip stress-mark accents
```

`ocr-pdf -C` runs it for you. The raw `<basename>.txt` is always kept, so
nothing is lost if a rule turns out to be wrong for a particular document —
edit the regexes at the top of the script if it is.

### `bin/fetch-tessdata`

Downloads official Tesseract models into a local directory (default
`./tessdata/`, git-ignored). `ocr-pdf` calls it automatically for any
language you ask for that is not there yet; you only need it directly to
pre-fetch or to choose a different model set:

```sh
bin/fetch-tessdata nld ell           # tessdata_best (default): most accurate
bin/fetch-tessdata -s fast nld       # tessdata_fast: ~2x faster, a bit less accurate
bin/fetch-tessdata -s std  nld       # tessdata: also has the legacy engine (--oem 0)
bin/fetch-tessdata -d ~/tessdata -f nld   # other directory, force re-download
```

It also drops `pdf.ttf` (a glyphless font Tesseract needs for the invisible
text layer of searchable PDFs) into the same directory.

## How the pipeline works

1. **Page count** — `pdfinfo` tells us how many pages there are; `-f`/`-t`
   select a range.
2. **Render** — every page is rasterised on its own with
   `pdftoppm -singlefile -f N -l N -r 300 -gray -png`, `-j` pages at a time
   through `xargs -P`. Rendering the *page* (rather than extracting the
   embedded image with `pdfimages`) is what makes this work for any PDF,
   including ones with several images per page, rotation, or vector text.
   300 dpi is Tesseract's sweet spot; the Psalterion scans are 241 dpi and
   are simply upsampled. With `-P`, the rendered image is piped through
   ImageMagick before it is stored.
3. **OCR** — `tesseract page-NNNN.png page-NNNN -l LANG --psm PSM` per page,
   again `-j` in parallel, writing both plain text and hOCR (the same text
   with the position of every line and word). Tesseract's stderr goes to
   `page-NNNN.log`. Outputs are written under a temporary name and renamed
   on success, so an existing `page-NNNN.txt` always means "finished"
   (blank pages produce empty files, which is correct).
4. **Blank lines** — one `hocr-text` run over all pages' hOCR writes
   `text/page-NNNN.txt`, with blank lines placed by line spacing (see
   [`hocr-text`](#binhocr-text)). This is cheap and redone every time;
   `-T` skips it and uses Tesseract's own `page-NNNN.txt`.
5. **Assemble** — the per-page texts are concatenated in order into
   `out/<basename>/<basename>.txt`. Tesseract's trailing form feed and
   blank lines are trimmed from each page; pages are then separated by
   `\f` (pdftotext convention) or, with `-m`, by a visible marker line.
6. **Optional extras** — `-s` asks Tesseract for a per-page PDF as well and
   `pdfunite` joins them; `-C` runs `clean-ocr`.

Steps 2 and 3 are cached. Each cache directory carries a `.stamp` with the
settings that produced it (DPI, image format, ImageMagick args, language,
PSM, config variables, tool versions); when the stamp does not match the
current invocation, that directory is wiped and rebuilt. The OCR cache
depends on the render settings too, so changing `-r` rebuilds both.

Parallelism defaults to the number of CPU cores. The 346-page Psalterion
takes about a minute on a 16-core machine (Tesseract itself is ~1 s/page).

## Directory layout

```
bin/
  ocr-pdf            driver (bash)
  ocr-photo          photos and scans: prep-photo + Kraken lines + Tesseract (Kraken's python)
  prep-photo         photo cleanup before OCR (python3 + numpy, Pillow, OpenCV)
  cer                character error rate against a transcription (python3, stdlib only)
  hocr-text          hOCR -> text, blank lines placed by line spacing (python3, stdlib only)
  clean-ocr          artifact filter (python3, stdlib only)
  fetch-tessdata     language-model downloader (bash + curl)
tessdata/            downloaded *.traineddata + pdf.ttf   (git-ignored)
photos/              tablet photos of pages: only the first is in git (Git LFS);
                     the others are git-ignored, to save LFS storage
pdf/                 liturgie.pdf, scans of pages in the same style (git-ignored)
models/              the fine-tuned Kraken model, made by training (git-ignored)
experiments/photo-ocr/  scripts behind PHOTO-OCR.md: evaluation, training lines, synthetic
                     lines, Tesseract and Kraken fine-tuning
work/<basename>/     cache                                (git-ignored)
  img/page-NNNN.png  rendered pages (~2 MB each at 300 dpi; ~760 MB for 346 pages)
  ocr/page-NNNN.txt  per-page OCR text, as Tesseract laid it out
  ocr/page-NNNN.hocr per-page OCR text with line and word positions
  text/page-NNNN.txt per-page text with blank lines placed by hocr-text
  ocr/page-NNNN.log  per-page Tesseract messages
  ocr/page-NNNN.pdf  per-page searchable PDF (with -s)
  prep.png           prep-photo output for photo <basename>.jpg
  flat.png           prep-photo --flat output (lighting flattened only)
  debug.png          prep-photo -d overlay
  lines.json         ocr-photo: every line's baseline, polygon and readings
  lines.png          ocr-photo -d overlay
out/<basename>/      results
  <basename>.txt        raw OCR text
  <basename>.clean.txt  after clean-ocr (with -C)
  <basename>.pdf        searchable PDF (with -s)
  <basename>.gt.txt     hand transcription, if made (for bin/cer and evalset.py)
```

`work/` is safe to delete at any time; `out/` is small and worth keeping (or
committing).

## Tuning and troubleshooting

**Which language?** Wrong or missing languages are the biggest single
source of errors — Tesseract's LSTM models carry a per-language dictionary
and character set. Look at a page first: `pdftoppm -r 60 -png -f 4 -l 4
doc.pdf p` and open `p-004.png`.

**Page segmentation (`-p`).** `3` (default) detects columns, headings and
paragraphs by itself and was best for the Psalterion. Try `4` for a single
column with varying font sizes, `6` for a uniform block of text (tables of
verses, poetry with no headings), `1` if pages may be rotated (needs the
`osd` model: `bin/fetch-tessdata osd`). Cheap to compare on a few pages:

```sh
for p in 3 4 6; do bin/ocr-pdf -l nld -f 200 -t 200 -p $p -o /tmp/psm$p -w /tmp/psm$p-w doc.pdf; done
```

**Resolution (`-r`).** 300 is right for ordinary book type. Go to 400 for
small print or footnotes; below 200 quality drops off sharply.

**Preprocessing (`-P`).** For clean scans, leave it off: Tesseract does its
own Otsu binarisation and every recipe tried on the Psalterion traded one
artifact for another (see below). For skewed, faint, or very dirty scans
these are good starting points (quote the whole argument):

```sh
-P '-deskew 40%'                                    # straighten crooked pages
-P '-threshold 60% -morphology Open Square:1'       # hard binarise + drop specks < 3px
-P '-lat 25x25-10%'                                 # adaptive threshold for uneven lighting
-P '-despeckle -despeckle'                          # gentle noise removal
-P '-shave 60x60'                                   # cut 60px off every edge (dark borders)
```

Tesseract also has built-in alternatives: `-c thresholding_method=2`
(Sauvola, adaptive) and `-c textord_heavy_nr=1` (aggressive noise removal).

**Other useful `-c` variables.** `preserve_interword_spaces=1` keeps runs of
spaces (tables); `tessedit_char_blacklist=|` forbids characters that never
occur in the text; `user_defined_dpi=300` if a page image lacks DPI
metadata; `page_separator=` to drop the form feed at the end of each page.

**Speed.** `bin/fetch-tessdata -s fast LANG` gives integer models that are
roughly twice as fast at a small accuracy cost; delete the matching
`tessdata/LANG.traineddata` first or use `-f`. Lower `-j` if the machine
gets starved of memory (each Tesseract process uses a few hundred MB).

**Searchable PDF size.** Tesseract embeds the page image it was given
without recompressing it. PNG input is stored losslessly (~1.7 MB/page for
these scans), so pass `-q 85` to render JPEG pages when you want the PDF:
`bin/ocr-pdf -l nld -s -q 85 doc.pdf` gives ~0.5 MB/page. Note this
changes the render settings, so the OCR cache is rebuilt, and JPEG input
very slightly changes the recognised text.

**"Error opening data file …/tessdata/xxx.traineddata".** The language
was not downloaded; run `bin/fetch-tessdata xxx` (network needed) or
check `TESSDATA_DIR`.

**One page failed.** The script stops with `ocr failed: page N (see
…/page-NNNN.log)`. Fix the cause and re-run; all other pages stay cached.

## Proofreading the result

OCR is never perfect; on a good scan expect a few wrong characters per
page and the occasional stray mark from dust. The cache is laid out for
side-by-side checking: `work/<basename>/img/page-0040.png` is exactly what
Tesseract saw when it wrote `work/<basename>/text/page-0040.txt`, and `-m`
markers give you the page number in the assembled file.

Handy checks:

```sh
# Pages with (almost) no text — blank pages, plates, or failures:
for t in work/Doc/ocr/page-*.txt; do
  c=$(tr -d '\f[:space:]' < "$t" | wc -c); [ "$c" -lt 100 ] && echo "$t: $c chars"; done

# What clean-ocr would change:
bin/clean-ocr -s out/Doc/Doc.txt | less

# Short "words" that are probably noise (macOS grep is byte-based in the C locale;
# set LC_ALL=en_US.UTF-8 or use python for non-ASCII patterns):
LC_ALL=en_US.UTF-8 grep -noE '\b[a-zA-Z]{1,2}\b' out/Doc/Doc.clean.txt | sort | uniq -c | sort -rn | head
```

Things `clean-ocr` deliberately does *not* touch, because they cannot be
distinguished from real text without reading it: stray marks *inside* a
line (`hen die : mij`), misread words (`bppen` for `lippen`), and dust that
became a quote next to a word (`‘voorkomt`). Those are for a human pass or a
dictionary-based spell check.

## The Psalterion run

Source: `~/dev/orthodoxy/Psalterion.pdf` — 346 pages, one 8-bit greyscale
JPEG per page at 241 dpi, no text layer (produced by "BookChanger 4.6.3").
Dutch throughout, a clean single-column serif setting with `*` marking the
half-verse, and a printed vertical rule in the left margin on many pages.

Command used (defaults everywhere else: 300 dpi, PSM 3, no preprocessing,
`tessdata_best` model):

```sh
bin/ocr-pdf -l nld -C -m '=== page %d ===' ~/dev/orthodoxy/Psalterion.pdf
```

Result: `out/Psalterion/Psalterion.txt` (raw, 11 315 lines / 51 581 words)
and `out/Psalterion/Psalterion.clean.txt`. Wall time 30 s with 16 jobs
(Tesseract 5.5.3; the first run, with 5.4.1, took 58 s and differed in
~650 words, nearly all of them margin noise).

Blank lines, counted in the cleaned text: with Tesseract's own layout (now
`-T`), 542 verses had a blank line right after their `*` half, and 57 times
a new verse (a line ending in `*`) followed a line ending in `.`/`;`/`:`
without a blank line, most of them missed stanza breaks. With `hocr-text`
those counts are 14 and 23; the latter includes false alarms, where a
half-verse wraps onto a second line. Most of what remains comes from OCR
errors (a stray `*`, a junk line) or skewed, dirty pages.
Pages 1 and 3 are blank (cover versos); page 2 is the title, 4 the preface,
5 the reprint notice, 6 onwards the psalms, followed by the nine biblical
canticles.

What was tried and rejected while tuning, all on pages 39/40/200:

- **PSM 4** — identical to PSM 3 here. **PSM 6** — worse: it kept the
  marginal rule as `|` in most lines and produced a junk first line.
- **ImageMagick binarisation** (`-threshold 50%`/`60%` + morphological
  open), **`-despeckle`**, **`-lat`** adaptive thresholding, greyscale
  **morphological opening** — each removed some `_`/`==` artifacts and
  introduced others (dropped `*` markers, new stray quotes, lost
  punctuation). No recipe was better across all three pages than the plain
  render, so none is used.
- **Tesseract `thresholding_method=1`/`2`** — same story; Sauvola (`2`)
  silently dropped a `*` on page 40. **`textord_heavy_nr=1`** — removed a
  few speck-quotes but lost a full stop and inserted a stray `i`.

What `clean-ocr` fixed on the raw output (660 lines changed or removed): 177 lines
beginning with `‚ `, 142 with `_ `, 87 with `| `, 40 with `. ` and a few
dozen with `'`/`:`/`!`/`;` — all the left-margin rule; 77 lines ending in
` |` (right page edge); 82 lines of pure junk (`'`, `_`, `—`, `| :` …);
5 stranded `*` re-attached.

What remains for a human pass: the occasional inline stray mark, a handful
of misread words per dozen pages (`bppen` for `lippen`, `WOrEN`, `Oe. en`
for a `*` on a dusty line),
and the top-of-page noise on a few dirty scans (`r-`, `Ln`, `zg` as a first
line). Compare against `work/Psalterion/img/page-NNNN.png` when in doubt.
