#!/bin/bash
# TGB2 experiment driver (val-selection first; test only for the chosen config)
set -e
cd /storage/gaoym/ex-graph-microtransaction-analysis
PY=.venv-cuda/bin/python
DIR=research/benchmark_tgb_v2
mkdir -p $DIR/logs

run() {
  local tag=$1; shift
  echo "=== $tag: $* ==="
  setsid bash -c "$PY $DIR/tgb_mlp2.py $* --tag $tag --device cuda:5 > $DIR/logs/tgb_mlp2_${tag}.log 2>&1" < /dev/null &
  echo "launched $tag pid $!"
}

# E1: 4M positives, 8 epochs (pipeline validation, ~25-35 min)
run v1a --train-subset 4000000 --epochs 8 --hidden 512 --eval-split val
