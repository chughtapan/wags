#!/usr/bin/env bash
set -uo pipefail

echo "=== Partial fill: D/vague (missing multi_turn_base_44) ==="
.venv/bin/python3 scripts/run_experiment.py \
  --subset D --condition vague \
  --test-ids multi_turn_base_44 \
  2>&1 | tee logs/D_vague_partial.log
echo ""

echo "=== Partial fill: D/null (missing 5 cases) ==="
.venv/bin/python3 scripts/run_experiment.py \
  --subset D --condition null \
  --test-ids multi_turn_base_4,multi_turn_base_18,multi_turn_base_40,multi_turn_base_42,multi_turn_base_44 \
  2>&1 | tee logs/D_null_partial.log
echo ""

echo "=== Running E (all 4 conditions) ==="
for condition in specific vague verbose null; do
  .venv/bin/python3 scripts/run_experiment.py \
    --subset E --condition "$condition" \
    2>&1 | tee "logs/E_${condition}.log"
  echo ""
done

echo "=== Done ==="
