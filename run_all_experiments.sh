#!/usr/bin/env bash

set -uo pipefail  # ❌ removed -e so it doesn't exit on error

SUBSETS=(D E)
CONDITIONS=(specific vague verbose null)

BASE_OUTPUT="outputs/feedback"
LOG_DIR="logs"
mkdir -p "$LOG_DIR"

# D/specific has a partial run (only multi_turn_base_0 started before the
# process died). Clear its raw output so the skip guard doesn't block it.
PARTIAL_D="outputs/feedback/D/specific/raw"
if [[ -f "${PARTIAL_D}/external_feedback.jsonl" ]]; then
  echo "🧹 Clearing partial D/specific output before rerun"
  rm -f "${PARTIAL_D}/external_feedback.jsonl"
  rm -f "${PARTIAL_D}/multi_turn_base_0_structured.jsonl"
fi

echo "=== Starting BFCL experiment sweep (D + E rerun) ==="

for subset in "${SUBSETS[@]}"; do
  for condition in "${CONDITIONS[@]}"; do

    OUTPUT_DIR="${BASE_OUTPUT}/${subset}/${condition}"
    RAW_DIR="${OUTPUT_DIR}/raw"

    # Skip completed
    if [[ -f "${RAW_DIR}/external_feedback.jsonl" ]]; then
      echo "⏭️  Skipping ${subset}/${condition} (already completed)"
      continue
    fi

    echo ""
    echo "🚀 Running ${subset}/${condition}"
    echo "----------------------------------------"

    LOG_FILE="${LOG_DIR}/${subset}_${condition}.log"

    # Run and capture exit code
    python scripts/run_experiment.py \
      --subset "$subset" \
      --condition "$condition" \
      2>&1 | tee "$LOG_FILE"

    EXIT_CODE=${PIPESTATUS[0]}

    if [[ $EXIT_CODE -ne 0 ]]; then
      echo "❌ FAILED ${subset}/${condition} (exit code: $EXIT_CODE)"
      echo "   See log: $LOG_FILE"
      continue
    fi

    echo "✅ Finished ${subset}/${condition}"
    echo "📄 Log saved to ${LOG_FILE}"

  done
done

echo ""
echo "🎉 D + E rerun complete (including failures)."