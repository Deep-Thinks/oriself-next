#!/bin/bash
# 启动 v2.5.4 benchmark（160 场 = 16 MBTI × 10 风格，与 v2.5.2/v2.5.3 baseline 可比）
# v2.5.4 修了 codex audit 抓到的 4 处 P0：
#   1. phase-exploring.md L20-23 维度定义改非问句句式（防 LLM 把维度描述当问句模板）
#   2. phase-exploring.md L43 + exemplary-session.md L123 旧 E/I 题 6 引用同步
#   3. CONVERGE.md 加 E 信号 keyword 解码 fallback（防 ESTJ_introspective 类创伤主线带偏）
#   4. lint 升级抓 "哪个更 X / 是 X 是 Y" 等隐式 A/B
#
# 跑完自动 mv results → results.v2.5.4_160，跑 metric 把 huai_pct 写入 logs。
# 用法：nohup bash run_v2.5.4.sh > logs/v2.5.4_nohup.log 2>&1 &

set -e
cd "$(dirname "$0")/.."
ORISELF_DIR="$(pwd)"

STAMP="$(date +%Y%m%d_%H%M%S)"
WRAPPER_LOG="benchmark/logs/v2.5.4_wrapper_${STAMP}.log"
METRIC_LOG="benchmark/logs/v2.5.4_metric_${STAMP}.log"

mkdir -p benchmark/logs

echo "===== v2.5.4 BENCHMARK START $(date) =====" | tee -a "$WRAPPER_LOG"
echo "oriself dir: $ORISELF_DIR" | tee -a "$WRAPPER_LOG"
echo "PID: $$" | tee -a "$WRAPPER_LOG"

# Phase 1 · 跑 benchmark
echo "" | tee -a "$WRAPPER_LOG"
echo "===== Phase 1 · benchmark.runner --styles-per-mbti 10 =====" | tee -a "$WRAPPER_LOG"
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

# Phase 2 · mv results → results.v2.5.4_160
echo "" | tee -a "$WRAPPER_LOG"
echo "===== Phase 2 · mv results → results.v2.5.4_160 =====" | tee -a "$WRAPPER_LOG"
if [ -d "benchmark/results.v2.5.4_160" ]; then
  echo "WARN · results.v2.5.4_160 已存在，备份为 results.v2.5.4_160.${STAMP}" | tee -a "$WRAPPER_LOG"
  mv "benchmark/results.v2.5.4_160" "benchmark/results.v2.5.4_160.${STAMP}"
fi
mv benchmark/results benchmark/results.v2.5.4_160
echo "Phase 2 OK · 数据在 benchmark/results.v2.5.4_160/" | tee -a "$WRAPPER_LOG"

# Phase 3 · 跑 metric。注意：metric mode 在阈值未达成时返回 1，
# 我们要继续 Phase 4，所以 || true。
echo "" | tee -a "$WRAPPER_LOG"
echo "===== Phase 3 · eval_probe_style.py --mode metric =====" | tee -a "$WRAPPER_LOG"
python3 benchmark/eval_probe_style.py --mode metric --run results.v2.5.4_160 \
  > "$METRIC_LOG" 2>&1 || true
echo "Phase 3 OK · metric 报告写入 $METRIC_LOG" | tee -a "$WRAPPER_LOG"

# Phase 4 · lint 留底
echo "" | tee -a "$WRAPPER_LOG"
echo "===== Phase 4 · eval_probe_style.py --mode lint (静态校验留底) =====" | tee -a "$WRAPPER_LOG"
python3 benchmark/eval_probe_style.py --mode lint 2>&1 | tee -a "$WRAPPER_LOG" || true

# Phase 5 · 同 baseline 对比 (head-line)
echo "" | tee -a "$WRAPPER_LOG"
echo "===== Phase 5 · 对 v2.5.2 / v2.5.3 baseline 对比摘要 =====" | tee -a "$WRAPPER_LOG"
{
  echo "v2.5.2 baseline:"
  head -20 benchmark/results.v2.5.2_160/summary.md
  echo ""
  echo "v2.5.3 prev:"
  head -20 benchmark/results.v2.5.3_160/summary.md
  echo ""
  echo "v2.5.4 NEW:"
  head -20 benchmark/results.v2.5.4_160/summary.md
} 2>&1 | tee -a "$WRAPPER_LOG" || true

echo "" | tee -a "$WRAPPER_LOG"
echo "===== ALL DONE $(date) =====" | tee -a "$WRAPPER_LOG"
echo "" | tee -a "$WRAPPER_LOG"
echo "查看："
echo "  wrapper 日志：    $WRAPPER_LOG"
echo "  metric 报告：     $METRIC_LOG"
echo "  benchmark summary: benchmark/results.v2.5.4_160/summary.md"
