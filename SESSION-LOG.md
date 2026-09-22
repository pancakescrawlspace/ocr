# Session log: OCR of phone photos

A chronological record of one working session (2026-09-22) on OCR of phone
photos of printed pages: what was tried, what went wrong, why, and what fixed
it, with the commands to reconstruct each step. The dead ends are in here on
purpose. The finished method is described in [PHOTO-OCR.md](PHOTO-OCR.md).

All numbers are character error rates (CER) against hand transcriptions,
measured with `bin/cer` (one page) or `experiments/photo-ocr/evalset.py` (all
transcribed pages). Commands are run from the repository root; `tessdata/`
holds the Tesseract models (`bin/fetch-tessdata nld`), and Kraken lives in
its own virtualenv, `~/.venvs/kraken` (Kraken 7.1.1, set up for the akafist
project).

## Contents

- [Part 1: one photo, Tesseract](#part-1-one-photo-tesseract)
- [Part 2: thirteen more photos, and Kraken's segmentation](#part-2-thirteen-more-photos-and-krakens-segmentation)
- [Part 3: training Kraken](#part-3-training-kraken)
- [Part 4: a scanned PDF as an independent test](#part-4-a-scanned-pdf-as-an-independent-test)
- [Part 5: fine-tuning Tesseract](#part-5-fine-tuning-tesseract)
- [Where it ended](#where-it-ended)
- [Lessons](#lessons)

## Part 1: one photo, Tesseract

**The question.** A phone photo of a printed page in a plastic sleeve
(`photos/20251128_143633.jpg`): how do you prepare it for OCR? First the
photo was measured (orientation, clipping, brightness, ink colours), then a
hand transcription was made (`out/20251128_143633/20251128_143633.gt.txt`) to
score every attempt against.

**Issue 1: Tesseract read nothing at all.** The camera stores the picture
sideways with an EXIF "rotate 90°" tag; viewers apply it, Tesseract (through
Leptonica) does not.

```sh
TESSDATA_PREFIX=tessdata tesseract photos/20251128_143633.jpg - -l nld --psm 4    # empty
python3 -c "from PIL import Image, ImageOps; ImageOps.exif_transpose(Image.open('photos/20251128_143633.jpg')).save('/tmp/oriented.png')"
TESSDATA_PREFIX=tessdata tesseract /tmp/oriented.png /tmp/oriented -l nld --psm 4
bin/cer out/20251128_143633/20251128_143633.gt.txt /tmp/oriented.txt            # 5.07%
```

**Issue 2: the obvious fix made things worse.** The photo seemed to suffer
from glare and uneven light, so the first step flattened the lighting
(dividing by an estimate of the bare paper). The CER went *up*, to 5.8–6.5%.
Dumping the image Tesseract actually binarises showed that its own
thresholding already coped, because nothing in the photo was burnt out:

```sh
TESSDATA_PREFIX=tessdata tesseract /tmp/oriented.png /tmp/dbg -l nld --psm 4 -c tessedit_write_images=true
# -> /tmp/dbg.processed.tif, the binarised page Tesseract read
```

*Lesson:* measure before fixing; the visible defect was not the costly one.

**Issue 3: the real culprit was the readers' pen marks.** Stress marks
above vowels became accents (`Hèer`), and a row of marks was merged into the
small-print line above it (`vergeving.` became `ie col`).

**Issue 4: red ink was not red enough for the red-channel trick.** The red
pen is dull and dark, dark in the red channel too. *Fix:* after white
balancing, compare *absorbance*: black ink absorbs red and green light alike
(ratio ~0.92), red ink absorbs far less red (~0.75).

**Issue 5: a colour threshold on single pixels ate letters.** Chromatic
aberration and JPEG colour subsampling give black strokes coloured fringes,
and a "hysteresis" mask grew from the underlines into the letters they
touched (9.24% CER). *Fix:* smooth the absorbance before the ratio and drop
small red pieces.

**Issue 6: finding text lines by ink density is fragile.** Several versions
of the line model failed in different ways (noise at the binder edge, `L:`
and `//` erased as marks, the ascender zone taken for a line). What worked
best: the x-height band as "rows at least half as dense as the densest row
nearby", and erasing a blob only with positive evidence of a line below it.

**Issue 7: a refactor changed the result.** Rewriting the experiment as
`bin/prep-photo` changed one rounding (a band extension of 11 px instead of
9) and the CER went from 2.19% to 2.88%. Every refactor needs the score re-run.

**Issue 8: stroke width does not separate pen from print** (marks 10 px,
letters 12 px median). Marks touching a letter stay; `clean-ocr -a` strips
the accents Tesseract makes of them.

End of part 1: 1.29% on that photo.

```sh
python3 -m pip install --user opencv-python-headless scipy     # for prep-photo
bin/prep-photo -d photos/20251128_143633.jpg                     # -> work/20251128_143633/prep.png, debug.png
TESSDATA_PREFIX=tessdata tesseract work/20251128_143633/prep.png - -l nld --psm 4 \
    -c 'tessedit_char_blacklist={}!|' | bin/clean-ocr -a > /tmp/p1.txt
bin/cer out/20251128_143633/20251128_143633.gt.txt /tmp/p1.txt    # 1.29%
```

**Housekeeping.** The ImageMagick binary on this machine failed to start (a
missing `libraw` library). Photos are stored with Git LFS:
`git lfs track "*.jpg"` (writes `.gitattributes`). Nothing else goes into LFS:
the scanned PDF (48 MB) and the trained Kraken model (23 MB) are git-ignored
(`pdf/`, `models/`), so as not to use LFS storage; the model can be rebuilt
with the commands in part 3. For the same reason the thirteen later photos are
git-ignored too (`/photos`); only the first one is in the repository.

## Part 2: thirteen more photos, and Kraken's segmentation

**Issue 9: the pipeline did not generalise.** On the new photos the error
rate ranged from 1% to 26%: two were blurred (camera shake), one angled with
small print, several had binder holes and a dark hand shadow. Tuning on one
page had hidden all of this. *Fix:* transcribe every page (14 photos, 347
lines), score all of them together, always.

**Issue 10: identical file sizes.** All photos are exactly 2,097,713 bytes,
which looks like copies. Checksums and EXIF timestamps showed they are
different photos; the tablet (Samsung SM-T220) pads its JPEGs.

```sh
md5 photos/*.jpg
python3 -c "from PIL import Image; im = Image.open('photos/20251128_143653.jpg'); print(im.getexif().get(0x0132), im.getexif().get(0x0110))"
```

**Issue 11: off-the-shelf Kraken models read this print badly.** The public
models were listed and two fetched:

```sh
K=~/.venvs/kraken/bin
$K/kraken list                                   # all models on Zenodo (slow, ~1 min)
$K/kraken show 10.5281/zenodo.13788177          # McCATMuS: print/handwriting/typescript, 16th-21st c.
$K/kraken get 10.5281/zenodo.13788177
$K/kraken get 10.5281/zenodo.10592716           # CATMuS-Print Large
# models land in ~/Library/Application Support/htrmopo/<uuid>/
$K/kraken -i work/20251128_143633/prep.png /tmp/k.txt segment -bl ocr -m <path to .mlmodel>
```

McCATMuS gave 15–17% CER, CATMuS-Print Large 4.8%, against 1.3% for
Tesseract. The reason Kraken did so well in the akafist project: there the
model was *trained on that book's own lines*, 16,799 of them. But Kraken's
*segmentation* found every line, even on the angled photo. It is available on
its own:

```sh
$K/kraken -i work/20251128_143749/prep.png /tmp/seg.json segment -bl     # baselines + polygons, JSON
$K/kraken -a -i work/20251128_143749/prep.png /tmp/seg.xml segment -bl   # the same as ALTO XML
```

**Issue 12: a hybrid that collapsed on one page.** Kraken finds and
straightens the lines, Tesseract reads each one (`--psm 7`, "a single text
line"). Better on most pages, but 77% CER on a blurred one: Kraken fills
everything outside a line's polygon with black, and on a light-grey line the
black border dominates Tesseract's threshold. Turning pure black into white
also erased real ink on sharp pages. *Proper fix:* run the same extraction on
an all-white page; that yields exactly the "outside" mask.

**Issue 13: an anti-aliased mask edge.** A thin grey outline remained along
the polygon, and Tesseract returned nothing for some lines. *Fix:* whiten
everything not fully inside, plus 2 px.

**Issue 14: Kraken's lines cut off final commas and full stops.** blla ends a
baseline at the last letter, so a line-final `,` or `.` is outside the line
image, and the polygon's lower edge clips comma tails (`,` becomes `.`). For
training this is poison: the transcription has a comma the image lacks, and
the model learns to invent commas (it did: `Haar Kind, is`). *Fix:* extend
each baseline by 0.4 line heights at both ends, recompute the polygons, and
add a strip under the baseline (0.35 of the line's own height). A plain band
of fixed height was tried first and was much worse with mixed print sizes.

**Issue 15: the TSV output config was missing.** `tesseract … tsv` failed
silently with the repo-local `tessdata/`, which has no `configs/tsv`, so
every line came back empty. `-c tessedit_create_tsv=1` does the same without
the config file.

**Issue 16: junk lines.** Kraken also finds "lines" in page edges and binder
holes. Tesseract's confidence does not separate them (a threshold of 40
already cost real text), but they are all tiny: dropping lines with fewer
than 3 letters, or fewer than 8 at confidence below 55, removed only junk.

This became `bin/ocr-photo`: 3.12% over the 14 photos, against 6.54% for
prep-photo + `tesseract --psm 4`.

**Issue 17: `ocr-photo` did not find Kraken.** It re-runs itself under the
Kraken virtualenv's python when `import kraken` fails, but first compared the
real paths of the two interpreters to avoid a loop, and a venv's `python` is
a symlink to the very same binary. *Fix:* an environment flag.

**Issue 18: the eraser ate letters on blurred photos.** The overlay
(`bin/ocr-photo -d …` writes `work/<name>/lines.png`) of the angled, blurred
page showed holes in letters where red underlines ran into them, and one
faint word gone entirely. *Fix:* find the lines on the cleaned image, but let
Tesseract read them from the image with only the lighting flattened
(`prep-photo --flat`): 3.12% → 2.65%, and no change on clean scans.

```sh
bin/ocr-photo -d photos/*.jpg                       # -> out/<name>/<name>.clean.txt, work/<name>/lines.{json,png}
experiments/photo-ocr/evalset.py                    # photos 2.65%
```

**Issue 19: zsh does not split words.** A test loop passed
`flags="--keep-red --keep-marks"` as `$flags`; zsh hands that over as *one*
argument, prep-photo refused it, and the variant silently produced nothing.
(The result was a nonsense 6.30% before the cause was found.)

## Part 3: training Kraken

The question was whether a Kraken model fine-tuned on these pages could beat
Tesseract, as it did in akafist.

**Setup.** Training lines are cut exactly as Kraken's recogniser sees them at
reading time (black outside the polygon) and paired with transcription lines
by similarity. Lines where the reader's pen changes a letter (a `g` written
over a `d`, a pasted correction slip) are left out of training: the image no
longer shows what the transcription says. They still count in evaluation.

```sh
~/.venvs/kraken/bin/python experiments/photo-ocr/build_lines.py work/kraken-lines $(ls photos | sed 's/\.jpg$//')
# -> work/kraken-lines/<name>/NNN.png + NNN.gt.txt, manifest.tsv (328 ok, 13 excluded, 6 partial, 19 unmatched)
```

To test on photos the model has not seen, the photos were split into two
halves (A and B, 7 photos each); a model trained on one half is scored on
the other.

**Issue 20: training on the GPU hung silently.** `ketos -d mps train` logged
its setup and then used 0% CPU, for minutes, both in the background and with
stdin closed. On the CPU it trains:

```sh
CP="$(ls ~/Library/Application\ Support/htrmopo/*/catmus-print-fondue-large.mlmodel)"
~/.venvs/kraken/bin/ketos -v -d cpu --threads 4 --workers 0 -s 1 train -f path \
    -t train_A.txt -i "$CP" --resize union -o model_A -B 8 --augment -q early --min-epochs 10 --lag 8 -N 40
```

(`-i` fine-tunes the given model, `--resize union` adds characters it lacks,
`-q early` stops when validation stops improving.) *Lesson:* check that a
background job actually uses CPU (`ps -o time,%cpu`).

**Issue 21: progress is invisible in a log file.** With output redirected,
ketos shows no progress bar; `-v` logs a "validation run … accuracy" line per
epoch, and `-o DIR` receives a checkpoint per epoch.

**Issue 22: Kraken 7 API changes.** A trained model (`.safetensors`, or a
checkpoint converted with `ketos convert -o m.safetensors checkpoint_NN.ckpt`)
cannot be loaded with the old `kraken.lib.models.load_any`; it takes
`kraken.tasks.RecognitionTaskModel.load_model`. Its inference also defaults to
`device='auto'` (the GPU) with worker processes, and hung like training did;
`RecognitionInferenceConfig(accelerator='cpu', device=1, num_line_workers=0)`
works (`device='cpu'` raises a TypeError in Lightning). See
`experiments/photo-ocr/kraken_read.py`.

**Issue 23: too little data.** Fine-tuned on 167 real lines, the model
reached 99% on its own validation lines but 4.9% on the other half of the
photos (Tesseract hybrid: 3.0%), with typical confusions (`rn`/`m`, `ri`/`n`,
`Ft` for `H`). On the sharp scans of part 4 the model trained on all 328
lines scored 7.8%, confidently wrong: it had learnt blurred photo lines. The
akafist model had 50 times more lines.

**Fix: synthetic lines.** 4,000 lines rendered in the page's typeface
(Arial) from Psalterion text, with pen-like strokes and underlines, at every
blur level:

```sh
python3 experiments/photo-ocr/synth.py 4000 work/kraken-synth
```

Fine-tuned on these plus the real lines (four times over), with 30 real lines
held out for validation, the model read the scans at 2.4% after one epoch
(from 7.8%). Epochs take about 13 minutes on the CPU.

```sh
python3 - <<'PY'     # training and validation lists: synthetic + real x4, 30 real lines held out
import random
rows = [l.rstrip('\n').split('\t') for l in open('work/kraken-lines/manifest.tsv')]
real = [r[1] for r in rows if r[3] == 'ok']
random.Random(3).shuffle(real)
synth = [l.strip() for l in open('work/kraken-synth/list.txt') if l.strip()]
open('work/kraken-train.txt', 'w').write('\n'.join(synth + real[30:] * 4) + '\n')
open('work/kraken-val.txt', 'w').write('\n'.join(real[:30]) + '\n')
PY
~/.venvs/kraken/bin/ketos -v -d cpu --threads 8 --workers 0 -s 1 train -f path \
    -t work/kraken-train.txt -e work/kraken-val.txt -i "$CP" --resize union \
    -o work/kraken-model -B 16 --augment -q early --min-epochs 4 --lag 4 -N 20 > work/kraken-train.log 2>&1
~/.venvs/kraken/bin/ketos convert -o models/liturgie-print.safetensors work/kraken-model/checkpoint_NN-0.XXXX.ckpt
~/.venvs/kraken/bin/python experiments/photo-ocr/kraken_read.py models/liturgie-print.safetensors /tmp/k liturgie-p16 …
```

**Issue 24: validation lines do not predict the test.** The 30 validation
lines are photo lines; on the scans the fold-A model was best after epoch 2
(1.9%) and worse after epoch 4 (2.4%), while its validation score rose. To
keep the scans an honest test, the checkpoint was nevertheless chosen by
validation score, never by scan score.

**Combining the engines.** Where the Tesseract and Kraken readings of a line
differ, the one with more words found in a Dutch vocabulary (the Psalterion
text) wins; Kraken readings with a confidence below 80 are not considered.
With a half-trained fold-A model this already gave 2.51% → 2.30% on the
unseen photos and 1.47% → 1.25% on the scans. `bin/ocr-photo -m MODEL` does
this.

## Part 4: a scanned PDF as an independent test

`pdf/liturgie.pdf` (77 pages) holds scans of pages in the same style. It has
no text layer, so it needed transcribing too; pages 16–17 and 21–26 have
text rather than musical notation (132 lines). They are never trained on,
which makes them the fairest test of anything trained on the photos.

```sh
pdffonts -f 16 -l 17 pdf/liturgie.pdf          # no fonts: pure scans, no text layer
pdfimages -list -f 16 -l 17 pdf/liturgie.pdf   # one 2449x3266 JPEG per page, 296 dpi
mkdir -p work/liturgie
for p in 16 17 21 22 23 24 25 26; do
  pdfimages -j -f $p -l $p pdf/liturgie.pdf work/liturgie/tmp && mv work/liturgie/tmp-000.jpg work/liturgie/liturgie-p$p.jpg
done
bin/ocr-photo work/liturgie/*.jpg
experiments/photo-ocr/evalset.py               # scans 1.47%
```

**Issue 25: the polygonizer fails at the image border.** On these scans the
text starts near the top edge; a lengthened baseline that touched the border
got no polygon, and a page lost all but one line. *Fix:* keep baselines 8 px
inside the image, and fall back to blla's own line when the polygonizer still
fails.

**The production Kraken model** (all photo lines plus the synthetic ones,
4 epochs, the checkpoint with the best validation score, 99.2%) reads the
scans at 1.45% on its own and at 1.30% combined with Tesseract (`ocr-photo -m`),
against 1.47% for Tesseract alone.

## Part 5: fine-tuning Tesseract

The question was whether Tesseract exposes its model so that it could be
reused with Kraken. It does: a `.traineddata` file is a container. Even
without Tesseract's tools its table of contents can be read (a count, then
64-bit offsets); the `version` entry gives the network spec,
`4.00.00alpha:nld:synth20170629:[1,36,0,1Ct3,3,16Mp3,3Lfys64Lfx96Lrx96Lfx192O1c1]`,
a model trained in 2017 on *synthetic* lines, like ours. Loading the network
into Kraken is not practical (no converter, and it would lose the 5.6 MB
dictionary Tesseract's decoder searches with), so Tesseract itself was
fine-tuned on our lines instead.

**Issue 26: no training tools.** MacPorts' tesseract has no training
variant. The libraries they need (ICU, pango, cairo, leptonica) were
installed, so Tesseract 5.5.3 was built from source with
`-DBUILD_TRAINING_TOOLS=ON` into `~/.local/opt/tesseract-training`, without
sudo and without touching the MacPorts installation (commands in the header
of `experiments/photo-ocr/train_tesseract.sh`).

**Issue 27: tesstrain refuses macOS's make.** "This version of GNU Make is too
low (3.81)": macOS ships make 3.81, tesstrain needs 4.2. MacPorts' `gmake`
(4.4.1) was already installed.

**Issue 28: the self-built Tesseract looked for its data in `./`.** Every
`tesseract … lstm.train` call failed with "Error opening data file
./eng.traineddata": the build does not know its install location.
`TESSDATA_PREFIX=~/.local/opt/tesseract-training/share/tessdata` fixes it;
that directory has the `lstm.train` config, and `eng` was fetched into it
because `lstm.train` runs with the default language.

**Issue 29: the fine-tuned model had no dictionary.** tesstrain's base model
for the new network was 11 KB: it builds the dictionary only from word lists
you supply, and silently builds none otherwise. `nld`'s dictionaries were
unpacked into word lists (478,341 words, archaic forms like `zijt` and
`menslievende` included) and the model rebuilt with them:

```sh
export PATH=~/.local/opt/tesseract-training/bin:$PATH
combine_tessdata -u tessdata/nld.traineddata work/tesstrain/nld-parts/nld.
dawg2wordlist work/tesstrain/nld-parts/nld.lstm-unicharset work/tesstrain/nld-parts/nld.lstm-word-dawg nld.word.txt
# (same for punc and number); then, for an already trained model:
mkdir -p work/tesstrain/dict/nld_lit_A        # combine_lang_model does not create it ("Error writing unicharset!!")
combine_lang_model --input_unicharset work/tesstrain/data/nld_lit_A/unicharset --script_dir work/tesstrain/data/langdata \
    --words nld.word.txt --puncs nld.punc.txt --numbers nld.number.txt --output_dir work/tesstrain/dict --lang nld_lit_A
lstmtraining --stop_training --continue_from work/tesstrain/data/nld_lit_A/checkpoints/nld_lit_A_checkpoint \
    --traineddata work/tesstrain/dict/nld_lit_A/nld_lit_A.traineddata --model_output tessdata/nld_lit_Ad.traineddata
```

For the production model the word lists were put in place before training
(`train_tesseract.sh` does that).

**Issue 30: zsh again.** `A="photos/a.jpg photos/b.jpg"; ocr-photo $A` passed
one argument (issue 19), and all three evaluation runs failed within
seconds, unnoticed because the output went to /dev/null. A zsh array,
`A=(photos/a.jpg photos/b.jpg)`, works.

**Issue 31: the fine-tuned model turned page edges into text.** On two
photos a page edge came out as a long string of letters (`Vee ee pe: SE ee
een Genee …`), too long for the junk rule, and cost one photo 18 points. A
junk test by vocabulary failed: the Psalterion "vocabulary" is OCR text and
contains `ee`, `pe`, `se`, `eee`, and even Tesseract's word list has them.
Confidence separates them (junk at 23–33, real lines at 48 and up; the stock
model never had a real line below 30), so lines below 30 are now dropped;
the stock model's results did not change.

Results (half-A models on half A's unseen photos; scans never trained on):

| | Unseen photos (7) | Scans |
|-|-------------------|-------|
| `nld`, stock | 2.51% | 1.47% |
| fine-tuned, no dictionary | 2.12% | 1.19% |
| fine-tuned, with dictionary | 1.85% | 1.28% |
| production model `nld_lit` (all photos) | (trained on them) | **0.86%** |

```sh
experiments/photo-ocr/train_tesseract.sh --holdout A nld_lit_A
experiments/photo-ocr/train_tesseract.sh nld_lit
bin/ocr-photo -l nld_lit --out /tmp/t work/liturgie/*.jpg && experiments/photo-ocr/evalset.py '/tmp/t/{}.clean.txt'
```

## Where it ended

| Pipeline | Photos (14) | Scans (8) |
|----------|-------------|-----------|
| `tesseract --psm 4`, EXIF-rotated | 11.84% | 9.69% |
| part 1: `prep-photo` + `tesseract --psm 4` | 6.54% | 2.68% |
| `ocr-photo` (Kraken's lines, stock Tesseract) | 2.65% | 1.47% |
| `ocr-photo -m` (plus fine-tuned Kraken) | 2.30%* | 1.30% |
| `ocr-photo -l nld_lit` (fine-tuned Tesseract) | 1.85%* | **0.86%** |

\* on the seven photos the half-A models did not see.

Kraken's contribution that lasted is its **segmentation**; its recognition,
even fine-tuned, is beaten by a fine-tuned Tesseract. The committed outputs
(`out/<name>/<name>.txt`, `.clean.txt`) are those of plain `ocr-photo`, which
anyone can reproduce from the repository; the fine-tuned models are
git-ignored (`models/`, `tessdata/`) and rebuilt by the scripts in
`experiments/photo-ocr/`.

## Lessons

- Measure first, on all the material, with transcriptions and a scorer; then
  change one thing at a time and re-measure.
- A visible defect is not necessarily the costly one (glare vs. pen marks).
- Tuning on one sample hides most failure modes; hold out data the method
  never saw (the other half of the photos, and the scans).
- Kraken's baseline segmentation is excellent on difficult photos; its
  recognition needs training data in the thousands of lines. Rendered lines
  in the right typeface are a cheap way to get there.
- Line images must contain everything their transcription contains, or a
  trained model learns to hallucinate.
- Two engines with different errors can be combined per line with a simple
  vocabulary check.
- Background jobs: check they really run (CPU time), and log progress where
  a file can see it. And check that a batch run actually produced output
  before reading its score (issue 30).
- A tool's defaults can silently drop what matters: tesstrain's model came
  without a dictionary, and nothing said so except its size.
- Shell details matter: zsh does not split `$var`; macOS has no `timeout`;
  `pkill -f PATTERN` also kills every process whose *command line* contains
  the pattern, including a watcher script that merely mentions it (this
  happened: stopping one training also killed the monitor of another).
