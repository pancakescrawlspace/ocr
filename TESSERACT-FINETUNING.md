# Fine-tuning Tesseract for the photographed liturgy pages

How Tesseract's Dutch model (`nld`) was fine-tuned on lines from the
photographed pages, and what it gained. Of everything tried in this
repository, the fine-tuned model reads these pages best. It is used with
`bin/ocr-photo -l nld_lit` and rebuilt with
`experiments/photo-ocr/train_tesseract.sh`. The wider story (why lines come
from Kraken, the Kraken models, the other experiments) is in
[PHOTO-OCR.md](PHOTO-OCR.md); the problems met on the way, in order, are in
[SESSION-LOG.md](SESSION-LOG.md), part 5.

| Test set | stock `nld` | fine-tuned `nld_lit` |
|----------|-------------|----------------------|
| 8 scanned pages, never trained on (4,549 characters) | 1.49% | **0.86%** |
| 7 photos the half-A model never saw (7,183 characters) | 2.59% | **1.89%** |
| a later photo, never trained on (697 characters) | 3.01% | **2.87%** |

(character error rates; all with `bin/ocr-photo`, which gives Tesseract one
line at a time; see "Evaluation" for what exactly was compared.)

## Contents

- [1. What a Tesseract model contains](#1-what-a-tesseract-model-contains)
- [2. Why fine-tune](#2-why-fine-tune)
- [3. Training data](#3-training-data)
- [4. Tools](#4-tools)
- [5. Keeping the dictionary](#5-keeping-the-dictionary)
- [6. The training run](#6-the-training-run)
- [7. Evaluation](#7-evaluation)
- [8. What is still wrong](#8-what-is-still-wrong)
- [9. Using the model](#9-using-the-model)
- [10. Doing it again](#10-doing-it-again)

## 1. What a Tesseract model contains

A `.traineddata` file is a container: a count, a table of 64-bit offsets,
then the components. `combine_tessdata -u` unpacks it; even without
Tesseract's tools the table can be read (a few lines of Python were enough).
`tessdata/nld.traineddata` (the "best" model, 8.9 MB) holds:

| Component | Size | What it is |
|-----------|------|------------|
| `lstm` | 3.3 MB | the neural network, with float weights |
| `lstm-unicharset` | 9 KB | the characters it can output (151 entries including specials) |
| `lstm-recoder` | 1 KB | how characters map to the network's output classes |
| `lstm-system-dawg` | 5.6 MB | the word list: 478,341 Dutch words, as a compact graph (DAWG) |
| `lstm-punc-dawg`, `lstm-number-dawg` | 5 KB, 1 KB | patterns for punctuation and numbers |
| `version` | 80 bytes | `4.00.00alpha:nld:synth20170629:[1,36,0,1Ct3,3,16Mp3,3Lfys64Lfx96Lrx96Lfx192O1c1]` |

The version string tells two things. The model was trained in 2017 on
*synthetic* lines (`synth20170629`), rendered text, as in this project. And
it gives the network in VGSL notation (the same notation Kraken uses, which
descends from Tesseract's):

| Layer | Meaning |
|-------|---------|
| `1,36,0,1` | input: one line image at a time, 36 px high, any width, greyscale |
| `Ct3,3,16` | 16 convolution filters of 3×3, tanh |
| `Mp3,3` | 3×3 max-pooling (the line is now 12 px high) |
| `Lfys64` | an LSTM of 64 units running *down* each column, summarising it to one vector |
| `Lfx96`, `Lrx96` | LSTMs of 96 units running forward and backward along the line |
| `Lfx192` | an LSTM of 192 units running forward |
| `O1c1` | the output: per position, a probability for each character (CTC), sized to the unicharset |

Tesseract does not simply take the network's most likely characters: its
decoder searches the network's output for the best string that the word
list, punctuation and number patterns allow, and only falls back on
non-words when nothing fits. For Dutch liturgical text, with archaic forms
(`zijt`, `menslievende`, `verrijzenis` are all in the list), that search
does a lot of the work.

**Why not run this network in Kraken?** The architecture could be written
down in Kraken's VGSL, but there is no converter for the weights (Tesseract's
own binary format, its own LSTM gate layout, its own input normalisation and
output recoding), and Kraken's decoder has no dictionary search, so a
converted network would be a weaker Tesseract. Fine-tuning Tesseract itself
keeps both.

## 2. Why fine-tune

With Kraken finding the lines, stock Tesseract read the 22 original test
pages at 2.65% (photos) and 1.47% (scans). A Kraken recognition model
fine-tuned on the same material did not beat it (4.5% and 2.4% alone). The
photographed pages differ from what `nld` was trained on in three ways a
fine-tune can address: one typeface (Arial) at all sizes, blur and grey ink
from tablet photos, and readers' pen marks (stress marks above vowels, red
underlines) that the stock model reads as accents, capitals or punctuation.

Fine-tuning continues training the existing network, starting from its
weights, with a low learning rate, on new lines. It keeps what the model
knows (the language, the dictionary, most letter shapes) and adapts it to the
new material; it needs far fewer lines than training from scratch.

## 3. Training data

All lines are cut exactly as `ocr-photo` gives them to Tesseract at reading
time, so that training and use see the same kind of image.

**Real lines** (`experiments/photo-ocr/build_lines.py --tesseract`):

- lines found by `ocr-photo`'s segmentation (Kraken's baselines, lengthened;
  polygons extended below the baseline) on `work/<name>/prep.png`;
- cut out of `work/<name>/flat.png` (lighting flattened, nothing erased) and
  straightened, white outside the line polygon;
- paired with the transcription line (`out/<name>/<name>.gt.txt`) that best
  matches Tesseract's reading of the line (similarity ≥ 0.6 on letters and
  digits, each line used once, lengths within −15%/+20%);
- 13 lines where a reader's pen changed a letter or a pasted correction slip
  covers the print are excluded (the image no longer shows what the
  transcription says); 6 partial and 19 unmatched lines (page edges, split
  lines) are not used either.

That leaves **328 lines** from the 14 photos; the half-A model used the 167
lines from the seven photos of half B.

**Synthetic lines** (`experiments/photo-ocr/synth.py --white 4000`): 4,000
lines of Psalterion text (`out/Psalterion/Psalterion.clean.txt`: the same
register, and not the text of any test page), sometimes with an `L: [n] `,
`[n] ` or `// ` prefix as on the pages, rendered in Arial (5% italic) at
42–80 px, with pen-like strokes above and underlines below random vowels
(which the transcription ignores), slight shear and rotation, Gaussian blur
from 0.4 to 3.5 px, grey ink on light paper, noise, and sometimes the lightest
grey clamped to white. With `--white` they have no black border (that is only
for Kraken).

**Mixing** (`experiments/photo-ocr/tesstrain_gt.py`): the real lines are
linked four times (they would otherwise be drowned by the synthetic ones),
the synthetic lines once: 328 × 4 + 4,000 = 5,312 lines for the production
model (half A: 167 × 4 + 4,000 = 4,668). tesstrain splits them at random
(seed 0) into 90% training and 10% evaluation lines: 4,780 and 532. (Its
lists end without a newline, so `wc -l` shows one line less each.)

tesstrain wants each line as `<id>.png` plus `<id>.gt.txt` in one directory.
It makes a `.box` file for each (the whole line as one box, with the text:
`generate_line_box.py`) and an `.lstmf` file (`tesseract <id>.png <id> --psm
13 lstm.train`: the image and text in Tesseract's training format).

## 4. Tools

The training tools (`lstmtraining`, `combine_tessdata`, `combine_lang_model`,
`dawg2wordlist`, …) are not part of the MacPorts package, which has no
variant for them. Tesseract 5.5.3 (the installed version) was built from
source with them, into `~/.local/opt/tesseract-training`, without sudo:

```sh
git clone --depth 1 --branch 5.5.3 https://github.com/tesseract-ocr/tesseract.git ~/.local/src/tesseract-5.5.3
cd ~/.local/src/tesseract-5.5.3 && mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_TRAINING_TOOLS=ON -DCMAKE_PREFIX_PATH=/opt/local \
  -DCMAKE_INSTALL_PREFIX=$HOME/.local/opt/tesseract-training -DGRAPHICS_DISABLED=ON \
  -DDISABLE_CURL=ON -DOPENMP_BUILD=OFF -DBUILD_TESTS=OFF
make -j6 && make install
```

(ICU, pango, cairo and leptonica came from MacPorts. OpenMP was left out, so
`lstmtraining` uses one core.) And tesstrain, the Makefile that drives the
tools:

```sh
git clone --depth 1 https://github.com/tesseract-ocr/tesstrain.git ~/.local/src/tesstrain
```

Three things had to be known:

- tesstrain needs GNU make 4.2 or newer; macOS has 3.81. MacPorts' `gmake`
  (4.4.1) works.
- The self-built `tesseract` looks for its data in `./`. `TESSDATA_PREFIX`
  must point at `~/.local/opt/tesseract-training/share/tessdata`, which holds
  the `lstm.train` config.
- `tesseract … lstm.train` loads the default language, English, even though
  it only converts images: `eng.traineddata` has to be in that directory
  (`bin/fetch-tessdata -d ~/.local/opt/tesseract-training/share/tessdata eng`).

## 5. Keeping the dictionary

tesstrain builds the new model's language data from word lists *you supply*
(`<model>.wordlist`, `.punc`, `.numbers` in its output directory). Without
them it silently builds a model **without any dictionary**: the base model it
created was 11 KB instead of 5.6 MB, and nothing else said so.

The fix is to unpack `nld`'s dictionaries into word lists and supply those:

```sh
export PATH=~/.local/opt/tesseract-training/bin:$PATH
combine_tessdata -u tessdata/nld.traineddata work/tesstrain/nld-parts/nld.
cd work/tesstrain/nld-parts
dawg2wordlist nld.lstm-unicharset nld.lstm-word-dawg   nld.word.txt     # 478,341 words
dawg2wordlist nld.lstm-unicharset nld.lstm-punc-dawg   nld.punc.txt     # 667 patterns
dawg2wordlist nld.lstm-unicharset nld.lstm-number-dawg nld.number.txt   # 124 patterns
# copied to work/tesstrain/data/nld_lit/nld_lit.{wordlist,punc,numbers} before training
```

`train_tesseract.sh` does this. A model already trained without them can
still get them: build a base model with the word lists
(`combine_lang_model`, into an output directory that must already exist) and
convert the final checkpoint with it (commands in SESSION-LOG.md, issue 29).
That is how the half-A model was measured both ways (below).

## 6. The training run

```sh
experiments/photo-ocr/train_tesseract.sh nld_lit                 # all 14 photos
experiments/photo-ocr/train_tesseract.sh --holdout A nld_lit_A   # half A left out, for testing
```

which runs, in `~/.local/src/tesstrain`:

```sh
gmake training MODEL_NAME=nld_lit START_MODEL=nld TESSDATA=$PWD/tessdata \
  DATA_DIR=$PWD/work/tesstrain/data MAX_ITERATIONS=8000 -j8
```

The parameters, most of them tesstrain's defaults:

| Parameter | Value | Note |
|-----------|-------|------|
| start model | `tessdata/nld.traineddata` ("best", float) | fine-tuning needs a float model; the "fast" integer models cannot be continued |
| network | `nld`'s, unchanged | tesstrain's `NET_SPEC` only applies when training from scratch |
| learning rate | 0.0001 | tesstrain's default for fine-tuning (0.002 from scratch) |
| iterations | 8,000 | one line per iteration: about 1.7 passes over the 4,780 training lines |
| characters | 150 | `nld`'s set covered every character in the training text ("Code range changed from 150 to 150") |
| page segmentation | `--psm 13` | raw line, for making the `.lstmf` files |
| split | 90% / 10%, seed 0 | |
| target error rate | 1% | tesstrain's default; it did not stop the run early |

The core call, as tesstrain issued it:

```sh
lstmtraining \
  --debug_interval 0 \
  --traineddata work/tesstrain/data/nld_lit/nld_lit.traineddata \
  --old_traineddata tessdata/nld.traineddata \
  --continue_from work/tesstrain/data/nld/nld_lit.lstm \
  --learning_rate 0.0001 \
  --model_output work/tesstrain/data/nld_lit/checkpoints/nld_lit \
  --train_listfile work/tesstrain/data/nld_lit/list.train \
  --eval_listfile work/tesstrain/data/nld_lit/list.eval \
  --max_iterations 8000 --target_error_rate 0.01
lstmtraining --stop_training \
  --continue_from work/tesstrain/data/nld_lit/checkpoints/nld_lit_checkpoint \
  --traineddata work/tesstrain/data/nld_lit/nld_lit.traineddata \
  --model_output work/tesstrain/data/nld_lit.traineddata
```

`--old_traineddata` lets `lstmtraining` map the old model's character set
onto the new one; `--stop_training` turns the checkpoint into a
`.traineddata` file (float weights, 8.9 MB with the dictionary; 3.3 MB
without). `train_tesseract.sh` copies it to `tessdata/nld_lit.traineddata`.

The error on the training lines as they were seen (Tesseract's "BCER train",
characters, and "BWER train", words):

| Lines seen | BCER train | BWER train |
|------------|------------|------------|
| 100 | 6.9% | 21.3% |
| 500 | 3.0% | 9.0% |
| 1,000 | 2.5% | 7.1% |
| 2,000 | 1.0% | 3.2% |
| 4,000 | 0.8% | 2.3% |
| 6,000 | 0.7% | 1.6% |
| 8,000 | 0.4% | 1.1% |

These are training errors and say nothing about unseen pages (and the 10%
evaluation lines contain copies of training lines, because the real lines are
linked four times). The evaluation that counts is the next section.

Time on this Mac: 1 to 4 minutes to make the `.box` and `.lstmf` files
(parallel), then 5 to 9 minutes of training on one core. The half-A model
took under 9 minutes in all, the production model under 10.

## 7. Evaluation

Three test sets, none of which a tested model was trained on:

- **Half A**: the photos were split into two halves of seven; the half-A
  model is trained on the lines of half B only and read the seven photos of
  half A.
- **The scans**: 8 pages of `pdf/liturgie.pdf` (pages 16–17, 21–26), the same
  kind of pages with the same kind of marks, but as sharp 296 dpi scans. No
  model was ever trained on them.
- **A later photo**, `photos/20260707_215411.jpg` (a different page, taken
  months later, a bluish cast, soft focus, and one line cut off by the frame).

Every run uses `bin/ocr-photo`, so the lines are the same and only the
Tesseract model differs (`-l`). Scores are character error rates against the
hand transcriptions (`experiments/photo-ocr/evalset.py`, `bin/cer`).

**The variants**, measured before the prep-photo fix (PHOTO-OCR.md, "A
fifteenth photo, and a fix to prep-photo"), with the models trained on half
B:

| Tesseract model | Half A (7 photos) | Scans |
|-----------------|-------------------|-------|
| `nld`, stock | 2.51% | 1.47% |
| fine-tuned, without dictionary | 2.12% | 1.19% |
| fine-tuned, with `nld`'s dictionary | 1.85% | 1.28% |
| fine-tuned with dictionary, combined with the fine-tuned Kraken model (`-m`) | 1.81% | |

The dictionary helped on the photos, probably because blur makes letters
ambiguous there and the word list settles them; on the sharp scans the model
without it was slightly better. The production model keeps the dictionary: blurred photos are what
this is for, and 0.1 points on the scans is a handful of characters.

**The production model** (trained on all 14 photos), on the scans and the
later photo, and the half-A model on half A, with the current prep-photo:

| | stock `nld` | fine-tuned | fine-tuned + Kraken (`-m`) |
|-|-------------|------------|----------------------------|
| scans (production model) | 1.49% | 0.86% | 0.88% |
| later photo (production model) | 3.01% | 2.87% | 2.87% |
| half A (half-A model) | 2.59% | 1.89% | |

On the later photo the gain is small: about half of its remaining errors are a
handwritten addition and letters cut off by the frame, which no reader can
get right, and it is a single page of 697 characters.

**Junk lines.** The fine-tuned model reads noise more willingly: on two
photos a page edge came out as a long string of letters (`Vee ee pe: SE ee
een Genee …`) instead of a few characters, and survived `ocr-photo`'s old
junk rule (fewer than 3 letters, or fewer than 8 at a confidence below 55).
Its confidence was 23–33, while every real line was at 48 or more (and at 30
or more with the stock model), so `ocr-photo` now also drops lines below 30.
Without that, one photo went from 1.0% to 18.8%.

## 8. What is still wrong

On the scans, the fine-tuned model's remaining errors are:

- **capitals after stress marks**: `Was`, `Van`, `Want`, `Uit` for `was`,
  `van`, `want`, `uit`. A pen stroke above a lower-case letter looks like the
  top of a capital. A likely cause: `synth.py` puts marks only above vowels,
  so the model never saw a mark above a `w` or `v` that had to be ignored;
- **headings**: `Troparion toon 7` read as `toon /`, `8` as `o`;
- **pen overwrites**: `pet graf` where a pen overwrote the `h` of `het`;
- **punctuation**: faint final commas lost or read as full stops, `//` read
  as `/` or `Il`.

On the later photo, half of the remaining errors are the reader's handwritten
"wereld zijt" after the last printed word, and two are the letters of `zij`
cut off by the frame.

## 9. Using the model

```sh
bin/ocr-photo -l nld_lit photos/*.jpg          # results in out/<name>/
bin/ocr-photo -l nld_lit --out /tmp/x page.jpg  # results elsewhere
```

The model is `tessdata/nld_lit.traineddata`, git-ignored like all of
`tessdata/` (it is 8.9 MB and rebuilt in ten minutes). It is an ordinary
Tesseract model: `tesseract line.png - -l nld_lit --psm 7` works too, with
`TESSDATA_PREFIX` pointing at `tessdata/`. It was trained on single lines
cut by `ocr-photo`; on whole pages with Tesseract's own layout analysis it
has not been tested.

## 10. Doing it again

For more pages of this binder: transcribe the new pages (correcting
`ocr-photo -l nld_lit` output is quickest), rerun `build_lines.py --tesseract`
on all photos, and `train_tesseract.sh`. Every page adds about 25 real lines;
there are 328 now, where the akafist project's Kraken model had 16,799.

For other material, the recipe carries over; the parts to adapt:

- **the typeface** in `synth.py` (any TrueType font), and its sizes;
- **the text** the synthetic lines are made of: text in the same language and
  register, but not the text of the test pages;
- **the marks**: `synth.py` draws stress-mark-like strokes and underlines;
  other annotations need other drawings;
- **the start model**: the "best" model for the language (`bin/fetch-tessdata`
  fetches those); and its dictionary, unpacked as in section 5.

Things worth trying that were not tried here:

- more iterations, or `EPOCHS=` instead of `MAX_ITERATIONS=`; a lower
  learning rate for a longer run;
- marks above capitals and consonants in `synth.py`, against the
  capitalisation errors;
- a cleaner lexicon for `-m` (the Psalterion text contains OCR junk);
- `lstmtraining --convert_to_int` for a smaller, faster integer model.

Checklist of what went wrong the first time: the training tools are missing
from the package; make is too old; `TESSDATA_PREFIX` must be set; `lstm.train`
needs `eng`; the dictionary is dropped without word lists; `combine_lang_model`
does not create its output directory; the fine-tuned model needs the
low-confidence junk rule.
