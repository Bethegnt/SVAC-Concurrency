#!/usr/bin/env bash
# ============================================================
# run_overnight.sh — SVAC Concurrency overnight batch runner
# Order: Nemotron → LLaMA → gemini-3.6 (last, after rate limit cools)
# Safe to kill/restart — checkpointing skips completed calls.
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

PYTHON=python3
LOG_DIR="results/logs"
mkdir -p "$LOG_DIR"

ts() { date '+%H:%M:%S'; }

banner() {
    echo ""
    echo "┌──────────────────────────────────────────┐"
    echo "│  [$(ts)]  $1"
    echo "└──────────────────────────────────────────┘"
}

progress() {
    echo ""
    echo "  📊 Progress snapshot ($(ts)):"
    for d in svac_llm_responses/*/; do
        slug=$(basename "$d")
        n=$(ls "$d"*.json 2>/dev/null | wc -l | tr -d ' ')
        echo "     $slug : $n / 375"
    done
}

run_openrouter_model() {
    local model_slug="$1"   # e.g. nvidia/nemotron-3-super-120b-a12b:free
    local friendly="$2"
    local sleep_s="$3"

    banner "Starting: $friendly (OpenRouter FREE)"

    # Patch config.py
    python3 -c "
import re, pathlib
cfg = pathlib.Path('api_callers/config.py')
txt = cfg.read_text()
txt = re.sub(r'OPENROUTER_MODEL\s*=\s*\".*\"',
             'OPENROUTER_MODEL = \"$model_slug\"', txt)
cfg.write_text(txt)
print('  Config → OPENROUTER_MODEL = $model_slug')
"
    local log="$LOG_DIR/${friendly}_$(date +%H%M).log"
    $PYTHON api_callers/svac_api_openrouter.py --sleep "$sleep_s" 2>&1 | tee "$log"
    progress
}

run_gemini_model() {
    local friendly="$1"
    local sleep_s="$2"
    banner "Starting: $friendly (Gemini FREE tier)"
    local log="$LOG_DIR/${friendly}_$(date +%H%M).log"
    $PYTHON api_callers/svac_api_gemini.py --sleep "$sleep_s" 2>&1 | tee "$log"
    progress
}

score_all() {
    banner "Scoring all models..."
    for d in svac_llm_responses/*/; do
        slug=$(basename "$d")
        n=$(ls "$d"*.json 2>/dev/null | wc -l | tr -d ' ')
        [ "$n" -lt 50 ] && echo "  ⚠️  $slug has only $n responses — skipping scoring" && continue
        echo "  Scoring: $slug ..."
        $PYTHON evaluation/svac_run_evaluation.py --model "$slug" 2>&1 | tail -5
    done
}

generate_figures() {
    banner "Generating comparison figures..."
    SCORES=($(ls results/scores/*_scores.json 2>/dev/null | sort))
    n=${#SCORES[@]}
    if [ "$n" -ge 2 ]; then
        $PYTHON analysis/svac_plot_results.py \
            --scores "${SCORES[0]}" \
            --scores2 "${SCORES[1]}" 2>&1
        echo "  ✅ Figures saved to analysis/figures/"
    elif [ "$n" -eq 1 ]; then
        $PYTHON analysis/svac_plot_results.py --scores "${SCORES[0]}" 2>&1
    else
        echo "  No score files yet."
    fi
}

# ════════════════════════════════════════════════
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   SVAC Overnight Batch — $(ts)       ║"
echo "╚══════════════════════════════════════════╝"
progress

# Step 1: NVIDIA Nemotron 120B — robust, big model
run_openrouter_model \
    "nvidia/nemotron-3-super-120b-a12b:free" \
    "nemotron-120b" \
    "3"

# Step 2: Meta LLaMA 3.1 8B — fast, lightweight
run_openrouter_model \
    "meta-llama/llama-3.1-8b-instruct:free" \
    "llama-3-1-8b" \
    "2"

# Step 3: gemini-3.6-flash — after 2+ hours, rate limit should have reset
banner "Waiting 10 min for Gemini rate limit to reset..."
sleep 600
run_gemini_model "gemini-3-6-flash" "5"

# Step 4: Score + Figures
score_all
generate_figures

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  ✅  OVERNIGHT COMPLETE — $(ts)       ║"
echo "║  Check: results/scores/ & figures/       ║"
echo "╚══════════════════════════════════════════╝"
