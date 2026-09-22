#!/usr/bin/env bash
#
# train_tesseract.sh - fine-tune Tesseract's nld model on the photographed pages' lines.
#
# Usage: experiments/photo-ocr/train_tesseract.sh [--holdout A] [MODEL_NAME]   [nld_lit]
#
# Uses the lines of work/tess-lines (build_lines.py --tesseract) and work/tess-synth
# (synth.py --white), links them into a tesstrain ground-truth directory
# (tesstrain_gt.py), unpacks nld's dictionary into word lists so that the new model
# keeps it (tesstrain builds a model *without* a dictionary unless word lists are
# supplied), fine-tunes from tessdata/nld.traineddata for 8000 iterations, and
# installs the result as tessdata/<MODEL_NAME>.traineddata, for
# `bin/ocr-photo -l <MODEL_NAME>`.
#
# Needs Tesseract's training tools and tesstrain; neither comes with the MacPorts
# package. They were set up like this (no sudo):
#   git clone --depth 1 --branch 5.5.3 https://github.com/tesseract-ocr/tesseract.git ~/.local/src/tesseract-5.5.3
#   cd ~/.local/src/tesseract-5.5.3 && mkdir build && cd build
#   cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_TRAINING_TOOLS=ON -DCMAKE_PREFIX_PATH=/opt/local \
#     -DCMAKE_INSTALL_PREFIX=$HOME/.local/opt/tesseract-training -DGRAPHICS_DISABLED=ON \
#     -DDISABLE_CURL=ON -DOPENMP_BUILD=OFF -DBUILD_TESTS=OFF
#   make -j6 && make install
#   bin/fetch-tessdata -d ~/.local/opt/tesseract-training/share/tessdata eng   # lstm.train needs a language
#   git clone --depth 1 https://github.com/tesseract-ocr/tesstrain.git ~/.local/src/tesstrain
# tesstrain needs GNU make >= 4.2 (macOS has 3.81; MacPorts' gmake works).

set -euo pipefail

holdout=()
if [ "${1:-}" = "--holdout" ]; then holdout=(--holdout "$2"); shift 2; fi
model="${1:-nld_lit}"

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
tools="${TESSERACT_TRAINING:-$HOME/.local/opt/tesseract-training}"
tesstrain="${TESSTRAIN:-$HOME/.local/src/tesstrain}"
data="$root/work/tesstrain/data"
parts="$root/work/tesstrain/nld-parts"
export PATH="$tools/bin:$PATH"
export TESSDATA_PREFIX="$tools/share/tessdata"   # the self-built tesseract looks in ./ otherwise

python3 "$root/experiments/photo-ocr/tesstrain_gt.py" ${holdout[@]+"${holdout[@]}"} "$data/$model-ground-truth"

mkdir -p "$parts" "$data/$model"
if [ ! -s "$parts/nld.word.txt" ]; then
  combine_tessdata -u "$root/tessdata/nld.traineddata" "$parts/nld."
  for d in word punc number; do
    dawg2wordlist "$parts/nld.lstm-unicharset" "$parts/nld.lstm-$d-dawg" "$parts/nld.$d.txt"
  done
fi
cp "$parts/nld.word.txt" "$data/$model/$model.wordlist"
cp "$parts/nld.punc.txt" "$data/$model/$model.punc"
cp "$parts/nld.number.txt" "$data/$model/$model.numbers"

cd "$tesstrain"
gmake training MODEL_NAME="$model" START_MODEL=nld TESSDATA="$root/tessdata" \
  DATA_DIR="$data" MAX_ITERATIONS=8000 -j8
cp "$data/$model.traineddata" "$root/tessdata/$model.traineddata"
echo "installed $root/tessdata/$model.traineddata"
