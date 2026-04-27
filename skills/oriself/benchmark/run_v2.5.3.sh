#!/bin/bash
# 启动 v2.5.3 benchmark（160 场 = 16 MBTI × 10 风格，与 v2.5.2_160 baseline 可比）
# 跑完自动 mv results → results.v2.5.3_160，跑 metric 把 huai_pct 写入 logs。
#
# 用法：nohup bash run_v2.5.3.sh > logs/v2.5.3_nohup.log 2>&1 &

set -e
cd "$(dirname "$0")/.."   # cd 到 skill-repo/skills/oriself
ORISELF_DIR="$(pwd)"

STAMP="$(date +%Y%m%d_%H%M%S)"
WRAPPER_LOG="benchmark/logs/v2.5.3_wrapper_${STAMP}.log"
METRIC_LOG="benchmark/logs/v2.5.3_metric_${STAMP}.log"

mkdir -p benchmark/logs

echo "===== v2.5.3 BENCHMARK START $(date) =====" | tee -a "$WRAPPER_LOG"
echo "oriself dir: $ORISELF_DIR" | tee -a "$WRAPPER_LOG"
echo "PID: $$" | tee -a "$WRAPPER_LOG"

# Phase 1 · 跑 benchmark（160 场，可耗时 30-90 分钟）
echo "" | tee -a "$WRAPPER_LOG"
echo "===== Phase 1 · 跑 benchmark.runner --styles-per-mbti 10 =====" | tee -a "$WRAPPER_LOG"
START_TS=$(date +%s)
if python3 -m benchmark.runner --styles-per-mbti 10 2>&1 | tee -a "$WRAPPER_LOG"; then
  END_TS=$(date +%s)
  echo "" | tee -a "$WRAPPER_LOG"
  echo "Phase 1 OK · 耗时 $((END_TS - START_TS)) 秒" | tee -a "$WRAPPER_LOG"
else
  echo "" | tee -a "$WRAPPER_LOG"
  echo "Phase 1 FAIL · 退出码 $?" | tee -a "$WRAPPER_LOG"
  exit 1
fi

# Phase 2 · mv results → results.v2.5.3_160
echo "" | tee -a "$WRAPPER_LOG"
echo "===== Phase 2 · mv results → results.v2.5.3_160 =====" | tee -a "$WRAPPER_LOG"
if [ -d "benchmark/results.v2.5.3_160" ]; then
  echo "WARN · results.v2.5.3_160 已存在，备份为 results.v2.5.3_160.${STAMP}" | tee -a "$WRAPPER_LOG"
  mv "benchmark/results.v2.5.3_160" "benchmark/results.v2.5.3_160.${STAMP}"
fi
mv benchmark/results benchmark/results.v2.5.3_160
echo "Phase 2 OK · 现在数据在 benchmark/results.v2.5.3_160/" | tee -a "$WRAPPER_LOG"

# Phase 3 · 跑 eval_probe_style metric mode
echo "" | tee -a "$WRAPPER_LOG"
echo "===== Phase 3 · eval_probe_style.py --mode metric =====" | tee -a "$WRAPPER_LOG"
python3 benchmark/eval_probe_style.py --mode metric --run results.v2.5.3_160 \
  > "$METRIC_LOG" 2>&1
echo "Phase 3 OK · metric 报告写入 $METRIC_LOG" | tee -a "$WRAPPER_LOG"
echo "" | tee -a "$WRAPPER_LOG"

# Phase 4 · 同时跑 lint mode 留底
echo "===== Phase 4 · eval_probe_style.py --mode lint (静态校验留底) =====" | tee -a "$WRAPPER_LOG"
python3 benchmark/eval_probe_style.py --mode lint 2>&1 | tee -a "$WRAPPER_LOG"

echo "" | tee -a "$WRAPPER_LOG"
echo "===== ALL DONE $(date) =====" | tee -a "$WRAPPER_LOG"
echo "" | tee -a "$WRAPPER_LOG"
echo "明早起来看：" | tee -a "$WRAPPER_LOG"
echo "  1. wrapper 全程日志：    $WRAPPER_LOG" | tee -a "$WRAPPER_LOG"
echo "  2. metric 结果（核心）： $METRIC_LOG" | tee -a "$WRAPPER_LOG"
echo "  3. benchmark summary:   benchmark/results.v2.5.3_160/summary.md" | tee -a "$WRAPPER_LOG"
echo "  4. 单 persona transcript: benchmark/results.v2.5.3_160/<PERSONA_ID>/transcript.md" | tee -a "$WRAPPER_LOG"
