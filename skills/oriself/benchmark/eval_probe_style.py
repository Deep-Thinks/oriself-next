"""
eval_probe_style.py · 探针风格 regression detector

为 v2.5.2 → v2.5.3 修复"R4-R8 X 还是 Y 句式 80-100%"问题而写。
朋友测试反馈"和十六型没区别甚至更麻烦"，根因是 oriself 在 phase-exploring/phase-deep
频繁用 A/B 二选一句式直接探针 MBTI 维度。SKILL.md v2.5.3 加了铁则 9（不主动二选一），
本脚本作为长期 regression suite 防退化。

两种模式：

  lint   (默认) 静态扫 skill-repo/skills/oriself/ 所有 markdown 的"还是"出现，
                区分合法（反例 / 内部判定 / [短回复 fallback] 标记）和违规（裸 A/B 问句）。
                成本：本地、毫秒级，0 LLM call。

  metric (--mode metric --run results.v2.5.X_160) 读已有 benchmark run 的
         turns/turn_NN.json，统计每轮 oriself_visible 的"X 还是 Y？" 句式
         出现率（huai_pct）。
         成本：本地、秒级，0 LLM call（复用已有 run 数据）。

目标阈值（v2.5.3 之后必须达成）：
  - lint:   全 skill markdown 违规 A/B 句式 < 5 处（current 0 期望）
  - metric: R4-R8 平均 huai_pct < 30%（v2.5.2 baseline 80-100%）
            任何单轮 huai_pct < 50%

退出码：
  0 = 全部通过
  1 = 任何 tier 未达标
  2 = 用法错误
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable

SKILL_ROOT = Path(__file__).resolve().parent.parent  # skill-repo/skills/oriself

# 检测 A/B 二选一 probe 句式。覆盖三类隐式 A/B：
#   1. "X 还是 Y？" 经典 A/B
#   2. "哪个更 X？" / "哪种 X 多一些？"  无"还是"字的隐式 A/B（codex v2.5.3 audit 抓到的漏网模式）
#   3. "是 X 是 Y？"  并列两个名词性短语作为选项
# 都要求问号收尾（避免抓陈述句里的连词"还是"）+ 跨句号不算（避免多句拼接误判）
HUAI_PATTERN = re.compile(r"[^。？！\n]{2,30}还是[^。？！\n]{2,30}[？?]")
NA_GE_PATTERN = re.compile(r"哪个更[^。？！\n]{1,15}[？?]")
NA_ZHONG_PATTERN = re.compile(r"哪种[^。？！\n]{1,20}多一些?[？?]")
SHI_X_SHI_Y_PATTERN = re.compile(r"是[^。？！\n，,是]{2,15}[，,]\s*是[^。？！\n]{2,15}[？?]")
# 联合模式：任何一个命中都算 A/B 违规
AB_PATTERNS = [HUAI_PATTERN, NA_GE_PATTERN, NA_ZHONG_PATTERN, SHI_X_SHI_Y_PATTERN]


def has_ab(text: str) -> bool:
    """统一入口：是否含 A/B 二选一句式（任一模式命中）。"""
    return any(p.search(text) for p in AB_PATTERNS)


def find_ab(text: str):
    """返回第一个命中的 match 对象（用于打印 sample），无命中返回 None。"""
    for p in AB_PATTERNS:
        m = p.search(text)
        if m:
            return m
    return None

# lint 模式：判断一行"还是"是否合法
LEGITIMATE_MARKERS = (
    "[短回复 fallback]",   # 显式标记的 fallback 题
    "**[短回复 fallback]**",
    "✅",                  # SKILL.md 铁则 9 / fallback 章节里的好示范标记
    "LLM-INTERNAL",        # 给 LLM 内部判定的句子（不对 user 说）
    "坏",                  # 反例标识（"坏:" / "❌" 附近）
    "❌",
    "禁",                  # 禁区列表
    "误读",                # mbti.md "常见的误读要避开" 段
    "听 TA",               # 给 LLM 内部判定用的描述
    "听 TA 自然吐",
    "看 TA",
    "区分",
    "～",                  # 删除线
    "~~",                  # markdown 删除线
    "作废",
    "v2.5.2 起作废",
    "维度定义",
    "（A/B 二选一）",      # 标注为反例
    "也坏",                # 反例标识扩展（reflective-listening 用到）
)


def is_legitimate_huai_line(line: str) -> tuple[bool, str]:
    """判断一行里的 A/B 句式是不是合法用法。返回 (合法, 原因)。

    v2.5.4 注：原来"维度定义"被判合法导致 LLM 直接当问句模板用了。
    现在 phase-exploring.md 维度定义已改成非"X 还是 Y"句式（"TA X；TA Y"），
    这条放宽规则不再需要——任何 A/B 问句模式无论行首结构都不合法。
    """
    stripped = line.strip()

    # 显式 markdown 标记
    for marker in LEGITIMATE_MARKERS:
        if marker in stripped:
            return True, f"含合法标记 '{marker}'"

    # 用户语料（**User** 开头）
    if "**User" in stripped:
        return True, "用户语料"

    # 不带问号 = 不是问句（陈述句里的"还是"作为连词，如"还是一轮一问"）
    if "？" not in stripped and "?" not in stripped:
        return True, "非问句（连词用法）"

    # 反例描述符（"问'X 还是 Y'"在引号内做反例引用）
    if "不要问" in stripped or "不要补" in stripped or "禁用" in stripped:
        return True, "反例引用"

    return False, ""


def lint_skill_markdown() -> int:
    """扫描所有 markdown，报告违规 A/B 句式。返回违规数。"""
    print("=" * 70)
    print("LINT MODE · 静态扫 skill-repo/skills/oriself/ 所有 markdown")
    print("=" * 70)

    violations: list[tuple[Path, int, str]] = []
    legit_count = 0
    total_files = 0

    for md_path in sorted(SKILL_ROOT.rglob("*.md")):
        if "/benchmark/" in str(md_path) or "/.git/" in str(md_path):
            continue
        total_files += 1
        rel = md_path.relative_to(SKILL_ROOT)
        with md_path.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                # 快速过滤：先看是否含任何 A/B 触发字（"还是" / "哪个" / "哪种"）+ "是…，是"
                if "还是" not in line and "哪个" not in line and "哪种" not in line and not re.search(r"是.{2,15}[，,]\s*是", line):
                    continue
                ok, reason = is_legitimate_huai_line(line)
                if ok:
                    legit_count += 1
                    continue
                # 用扩展 regex 看是否真有 A/B 问句模式（"X 还是 Y？" / "哪个更 X？" / "是 X 是 Y？"）
                if has_ab(line):
                    violations.append((rel, lineno, line.rstrip()))

    print(f"\n扫描 {total_files} 个 markdown 文件")
    print(f"合法'还是'用法：{legit_count} 处")
    print(f"违规 A/B 问句句式：{len(violations)} 处\n")

    if violations:
        print("VIOLATIONS:")
        for rel, lineno, text in violations:
            print(f"  {rel}:{lineno}  {text[:120]}")
            if len(text) > 120:
                print(f"  {' ' * (len(str(rel)) + len(str(lineno)) + 4)}…")
    else:
        print("（无）")

    print()
    threshold = 5
    if len(violations) > threshold:
        print(f"FAIL · 违规 {len(violations)} > 阈值 {threshold}")
        return 1
    print(f"PASS · 违规 {len(violations)} <= 阈值 {threshold}")
    return 0


def measure_benchmark_run(run_dir: Path) -> int:
    """读已有 benchmark run 的 turns/，统计每轮 oriself_visible huai_pct。"""
    print("=" * 70)
    print(f"METRIC MODE · 分析 {run_dir.relative_to(SKILL_ROOT)}/")
    print("=" * 70)

    if not run_dir.is_dir():
        print(f"错误：目录不存在 {run_dir}")
        return 2

    persona_dirs = [p for p in run_dir.iterdir() if p.is_dir()]
    if not persona_dirs:
        print(f"错误：{run_dir} 下没有 persona 子目录")
        return 2

    # round → [oriself_text]
    by_round: dict[int, list[str]] = {}
    huai_by_round: dict[int, list[bool]] = {}
    persona_count = 0

    for persona in sorted(persona_dirs):
        turns_dir = persona / "turns"
        if not turns_dir.is_dir():
            continue
        persona_count += 1
        for turn_file in sorted(turns_dir.glob("turn_*.json")):
            try:
                with turn_file.open(encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            r = data.get("round")
            text = data.get("oriself_visible") or ""
            if not isinstance(r, int) or not text:
                continue
            by_round.setdefault(r, []).append(text)
            huai_by_round.setdefault(r, []).append(bool(has_ab(text)))

    if not persona_count:
        print(f"错误：{run_dir} 下找不到 turns/turn_*.json")
        return 2

    print(f"\n扫描 {persona_count} 位 persona，共 {sum(len(v) for v in by_round.values())} 轮 oriself 输出\n")
    print(f"{'Round':>6} | {'N':>5} | {'huai_pct':>9} | sample violation")
    print("-" * 70)

    fails: list[str] = []
    r4_r8_pcts: list[float] = []

    for r in sorted(by_round.keys()):
        texts = by_round[r]
        flags = huai_by_round[r]
        n = len(texts)
        pct = sum(flags) / n if n else 0.0
        # sample 一条违规
        sample = ""
        for t, f in zip(texts, flags):
            if f:
                m = find_ab(t)
                sample = m.group(0) if m else t[:60]
                break

        flag_marker = ""
        if 4 <= r <= 8:
            r4_r8_pcts.append(pct)
            if pct >= 0.5:
                flag_marker = " ⚠ R4-8单轮>=50%"
                fails.append(f"R{r} pct={pct:.0%} >= 50%")

        print(f"R{r:>4} | {n:>5} | {pct:>8.0%} | {sample[:60]}{flag_marker}")

    if r4_r8_pcts:
        avg = sum(r4_r8_pcts) / len(r4_r8_pcts)
        print(f"\nR4-R8 平均 huai_pct: {avg:.0%}")
        if avg >= 0.30:
            fails.append(f"R4-R8 平均 {avg:.0%} >= 30%")
            print(f"FAIL · R4-R8 平均 {avg:.0%} >= 30% 阈值")
        else:
            print(f"PASS · R4-R8 平均 {avg:.0%} < 30% 阈值")

    if fails:
        print("\nFAILURES:")
        for f in fails:
            print(f"  - {f}")
        return 1

    print("\nPASS · 全部 tier 通过")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="eval_probe_style.py",
        description="探针风格 regression detector（lint / metric 两模式）",
    )
    parser.add_argument(
        "--mode",
        choices=("lint", "metric"),
        default="lint",
        help="lint=纯 grep；metric=读 benchmark run 算 huai_pct",
    )
    parser.add_argument(
        "--run",
        default="results.v2.5.2_160",
        help="metric 模式下要分析的 benchmark run 目录名（在 benchmark/ 下找）",
    )
    args = parser.parse_args(argv)

    if args.mode == "lint":
        return lint_skill_markdown()

    benchmark_dir = Path(__file__).resolve().parent
    run_dir = benchmark_dir / args.run
    return measure_benchmark_run(run_dir)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
