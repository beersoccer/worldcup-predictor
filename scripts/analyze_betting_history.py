#!/usr/bin/env python3
"""分析世界杯期间投注记录，输出基础统计与资金效率指标。

输入: docs/betting_history.csv
输出: docs/betting_analysis_report.md
       docs/betting_analysis_summary.json
       docs/betting_analysis.html

本金默认 1200 元，可通过 --capital 覆盖。

指标定义:
  - 资金周转率 = 总投注金额 / 本金
  - 资金使用率(峰值) = 单日投注占用峰值 / 本金  （按开赛日汇总）
  - 资金使用率(均值) = 平均单笔投注金额 / 本金
  - ROI = 最终赢利 / 本金
  - 投注收益率(Yield) = 最终赢利 / 总投注金额

场次归类:
  - 赢: WIN, WIN_HALF
  - 亏: LOSE, LOSE_HALF
  - 退还: DRAW
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "docs" / "betting_history.csv"
DEFAULT_REPORT = ROOT / "docs" / "betting_analysis_report.md"
DEFAULT_JSON = ROOT / "docs" / "betting_analysis_summary.json"
DEFAULT_HTML = ROOT / "docs" / "betting_analysis.html"

STATUS_WIN = {"WIN", "WIN_HALF"}
STATUS_LOSE = {"LOSE", "LOSE_HALF"}
STATUS_REFUND = {"DRAW"}


@dataclass
class Bet:
    bet_id: str
    status: str
    odds: float
    stake: float
    pnl: float
    kickoff: str | None
    placed: str | None
    market: str
    selection: str
    match: str


def _parse_cn_date(text: str, pattern: str) -> str | None:
    m = re.search(pattern, text)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return f"{y:04d}-{mo:02d}-{d:02d}"


def _market_type(desc: str) -> str:
    if "让球" in desc:
        return "让球盘"
    if "大小" in desc:
        return "大小盘"
    if "输赢" in desc:
        return "输赢盘"
    return "其他"


def _selection_line(desc: str) -> str:
    return desc.splitlines()[0].strip() if desc else ""


def _match_line(desc: str) -> str:
    m = re.search(r"-\s+(.+?)\s+国际足联", desc.replace("\r", ""))
    return m.group(1).strip() if m else ""


def load_bets(csv_path: Path) -> list[Bet]:
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))

    if not rows:
        raise ValueError(f"空文件: {csv_path}")

    bets: list[Bet] = []
    for row in rows[1:]:
        if not row or not row[0].strip() or row[0].strip() == "总计":
            continue
        while len(row) < 6:
            row.append("")

        head = row[0].strip()
        m = re.match(r"^(\d+)\s+(\S+)$", head)
        if not m:
            raise ValueError(f"无法解析投注头: {head!r}")
        bet_id, status = m.group(1), m.group(2)

        timeline, desc, odds_s, stake_s, pnl_s = row[1], row[2], row[3], row[4], row[5]
        odds_m = re.search(r"([\d.]+)", odds_s)
        stake_m = re.search(r"([\d.]+)", stake_s)
        if not odds_m or not stake_m:
            raise ValueError(f"无法解析赔率/金额: id={bet_id}")

        bets.append(
            Bet(
                bet_id=bet_id,
                status=status,
                odds=float(odds_m.group(1)),
                stake=float(stake_m.group(1)),
                pnl=float(pnl_s),
                kickoff=_parse_cn_date(desc, r"(\d{4})年(\d{1,2})月(\d{1,2})日"),
                placed=_parse_cn_date(timeline, r"已下注 - (\d{4})年(\d{1,2})月(\d{1,2})日"),
                market=_market_type(desc),
                selection=_selection_line(desc),
                match=_match_line(desc),
            )
        )
    return bets


def analyze(bets: list[Bet], capital: float) -> dict:
    if not bets:
        raise ValueError("没有可分析的投注记录")

    status_counts = Counter(b.status for b in bets)
    total_stake = sum(b.stake for b in bets)
    total_pnl = sum(b.pnl for b in bets)
    n = len(bets)

    win_n = sum(status_counts[s] for s in STATUS_WIN)
    lose_n = sum(status_counts[s] for s in STATUS_LOSE)
    refund_n = sum(status_counts[s] for s in STATUS_REFUND)

    # 按开赛日汇总占用（同日多场并行占用）
    by_kickoff: dict[str, float] = defaultdict(float)
    by_kickoff_n: dict[str, int] = defaultdict(int)
    for b in bets:
        key = b.kickoff or "unknown"
        by_kickoff[key] += b.stake
        by_kickoff_n[key] += 1
    peak_day, peak_exposure = max(by_kickoff.items(), key=lambda x: x[1])

    avg_stake = total_stake / n
    turnover = total_stake / capital
    util_peak = peak_exposure / capital
    util_avg = avg_stake / capital
    roi = total_pnl / capital
    yield_rate = total_pnl / total_stake

    # 有效胜率：全赢=1，半赢/半输/退还=0.5，全输=0
    half_credit = {"WIN_HALF", "LOSE_HALF", "DRAW"}
    effective_wins = sum(
        1.0 if b.status == "WIN" else 0.5 if b.status in half_credit else 0.0 for b in bets
    )
    win_rate = win_n / n
    effective_win_rate = effective_wins / n

    by_market = defaultdict(lambda: {"n": 0, "stake": 0.0, "pnl": 0.0})
    for b in bets:
        m = by_market[b.market]
        m["n"] += 1
        m["stake"] += b.stake
        m["pnl"] += b.pnl

    dates = sorted(d for d in by_kickoff if d != "unknown")
    period = {
        "first_kickoff": dates[0] if dates else None,
        "last_kickoff": dates[-1] if dates else None,
        "active_days": len(dates),
    }

    return {
        "capital": capital,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "period": period,
        "counts": {
            "bets": n,
            "win": win_n,
            "lose": lose_n,
            "refund": refund_n,
            "by_status": dict(status_counts),
            "win_rate": round(win_rate, 6),
            "effective_win_rate": round(effective_win_rate, 6),
        },
        "amounts": {
            "total_stake": round(total_stake, 2),
            "total_pnl": round(total_pnl, 2),
            "avg_stake": round(avg_stake, 2),
            "max_stake": round(max(b.stake for b in bets), 2),
            "min_stake": round(min(b.stake for b in bets), 2),
            "avg_odds": round(sum(b.odds for b in bets) / n, 4),
            "ending_bankroll": round(capital + total_pnl, 2),
        },
        "metrics": {
            "turnover_rate": round(turnover, 6),
            "utilization_peak": round(util_peak, 6),
            "utilization_avg": round(util_avg, 6),
            "roi": round(roi, 6),
            "yield": round(yield_rate, 6),
            "peak_day": peak_day,
            "peak_day_exposure": round(peak_exposure, 2),
            "peak_day_bets": by_kickoff_n[peak_day],
        },
        "by_market": {
            k: {
                "n": v["n"],
                "stake": round(v["stake"], 2),
                "pnl": round(v["pnl"], 2),
                "roi_on_stake": round(v["pnl"] / v["stake"], 6) if v["stake"] else 0.0,
            }
            for k, v in sorted(by_market.items())
        },
        "definitions": {
            "turnover_rate": "总投注金额 / 本金",
            "utilization_peak": "单日投注占用峰值 / 本金（按开赛日汇总）",
            "utilization_avg": "平均单笔投注金额 / 本金",
            "roi": "最终赢利 / 本金",
            "yield": "最终赢利 / 总投注金额",
            "win": "WIN + WIN_HALF",
            "lose": "LOSE + LOSE_HALF",
            "refund": "DRAW",
        },
    }


def render_report(result: dict) -> str:
    c = result["counts"]
    a = result["amounts"]
    m = result["metrics"]
    p = result["period"]
    status = c["by_status"]

    lines = [
        "# 世界杯投注记录分析报告",
        "",
        f"生成时间: {result['generated_at']}",
        f"分析区间: {p['first_kickoff']} ~ {p['last_kickoff']}（有效开赛日 {p['active_days']} 天）",
        f"本金: **{result['capital']:.2f}** 元",
        "",
        "## 1. 基础统计",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
        f"| 投注场次 | {c['bets']} |",
        f"| 赢场次（含半赢） | {c['win']} |",
        f"| 亏场次（含半输） | {c['lose']} |",
        f"| 退还场次 | {c['refund']} |",
        f"| 总投注金额 | {a['total_stake']:.2f} |",
        f"| 最终赢利金额 | {a['total_pnl']:+.2f} |",
        f"| 期末资金 | {a['ending_bankroll']:.2f} |",
        f"| 平均单笔投注 | {a['avg_stake']:.2f} |",
        f"| 单笔投注区间 | {a['min_stake']:.2f} ~ {a['max_stake']:.2f} |",
        f"| 平均赔率（港式） | {a['avg_odds']:.3f} |",
        f"| 胜率（赢场/总场） | {c['win_rate']*100:.2f}% |",
        f"| 有效胜率（半场按 0.5） | {c['effective_win_rate']*100:.2f}% |",
        "",
        "### 结算明细",
        "",
        "| 状态 | 场次 |",
        "|---|---:|",
    ]
    for key in ("WIN", "WIN_HALF", "DRAW", "LOSE_HALF", "LOSE"):
        lines.append(f"| {key} | {status.get(key, 0)} |")

    lines += [
        "",
        "## 2. 资金效率指标",
        "",
        "| 指标 | 数值 | 说明 |",
        "|---|---:|---|",
        f"| 资金周转率 | {m['turnover_rate']:.2f}x | {result['definitions']['turnover_rate']} |",
        f"| 资金使用率（峰值） | {m['utilization_peak']*100:.2f}% | {result['definitions']['utilization_peak']}；峰值日 {m['peak_day']}，占用 {m['peak_day_exposure']:.2f} 元 / {m['peak_day_bets']} 笔 |",
        f"| 资金使用率（均值） | {m['utilization_avg']*100:.2f}% | {result['definitions']['utilization_avg']} |",
        f"| ROI | {m['roi']*100:.2f}% | {result['definitions']['roi']} |",
        f"| 投注收益率 Yield | {m['yield']*100:.2f}% | {result['definitions']['yield']} |",
        "",
        "## 3. 盘口拆分",
        "",
        "| 盘口 | 场次 | 投注额 | 赢利 | Yield |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, row in result["by_market"].items():
        lines.append(
            f"| {name} | {row['n']} | {row['stake']:.2f} | {row['pnl']:+.2f} | {row['roi_on_stake']*100:.2f}% |"
        )

    lines += [
        "",
        "## 4. 结论摘要",
        "",
        f"- 以 {result['capital']:.0f} 元本金滚动，累计投注 **{a['total_stake']:.2f}** 元，"
        f"周转 **{m['turnover_rate']:.2f}** 倍，最终净盈利 **{a['total_pnl']:+.2f}** 元。",
        f"- 相对本金 ROI 为 **{m['roi']*100:.2f}%**；相对流水 Yield 为 **{m['yield']*100:.2f}%**。",
        f"- 共 {c['bets']} 笔：赢 {c['win']} / 亏 {c['lose']} / 退还 {c['refund']}；"
        f"峰值日资金占用约本金的 **{m['utilization_peak']*100:.1f}%**。",
        "",
    ]
    return "\n".join(lines)


def render_html(result: dict) -> str:
    """生成 Pitch Night 风格的自包含可视化页面。"""
    data_json = json.dumps(result, ensure_ascii=False)
    return _HTML_TEMPLATE.replace("__DATA_JSON__", data_json)


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>World Cup Book — 投注战绩</title>
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Source+Sans+3:wght@400;600;700&display=swap" rel="stylesheet" />
<style>
:root {
  --pitch: #0d2818;
  --pitch-mid: #1a5c3a;
  --ink: #06140c;
  --fog: #c8dcc8;
  --gold: #d4a017;
  --profit: #3ecf7a;
  --loss: #c44b3c;
  --half: #8fae72;
  --refund: #6b8f71;
  --line: rgba(212, 160, 23, 0.28);
  --text: #e8f2e8;
  --muted: #8aad8a;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body {
  font-family: "Source Sans 3", system-ui, sans-serif;
  color: var(--text);
  background:
    linear-gradient(180deg, #0a1f12 0%, var(--pitch) 38%, var(--ink) 100%);
  min-height: 100vh;
  line-height: 1.5;
}
body::before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  opacity: 0.07;
  background-image: repeating-linear-gradient(
    90deg,
    transparent,
    transparent 48px,
    rgba(255,255,255,0.35) 48px,
    rgba(255,255,255,0.35) 49px
  );
  z-index: 0;
}
.wrap {
  position: relative;
  z-index: 1;
  width: min(1080px, 92vw);
  margin: 0 auto;
  padding: 0 0 4.5rem;
}
.display { font-family: "Bebas Neue", sans-serif; letter-spacing: 0.04em; }

/* Hero — one composition */
.hero {
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 3.5rem 0 2.5rem;
  animation: rise 0.9s ease-out both;
}
@keyframes rise {
  from { opacity: 0; transform: translateY(18px); }
  to { opacity: 1; transform: translateY(0); }
}
.brand {
  font-family: "Bebas Neue", sans-serif;
  font-size: clamp(2.8rem, 8vw, 5.2rem);
  line-height: 0.95;
  color: var(--gold);
  text-shadow: 0 2px 24px rgba(212, 160, 23, 0.25);
}
.tagline {
  margin-top: 0.85rem;
  max-width: 28rem;
  color: var(--fog);
  font-size: 1.05rem;
  font-weight: 400;
}
.period {
  margin-top: 1.4rem;
  color: var(--muted);
  font-size: 0.92rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.hero-numbers {
  margin-top: 2.8rem;
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 1.5rem 2.5rem;
  align-items: end;
}
@media (max-width: 720px) {
  .hero-numbers { grid-template-columns: 1fr; }
}
.pnl-block .label {
  color: var(--muted);
  font-size: 0.85rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.pnl-value {
  font-family: "Bebas Neue", sans-serif;
  font-size: clamp(3.6rem, 12vw, 7rem);
  line-height: 0.9;
  color: var(--profit);
  margin-top: 0.2rem;
}
.pnl-value.neg { color: var(--loss); }
.bankroll-flow {
  margin-top: 0.75rem;
  color: var(--fog);
  font-size: 1.05rem;
}
.bankroll-flow strong { color: var(--gold); font-weight: 700; }
.roi-block {
  text-align: right;
  padding-bottom: 0.35rem;
  border-left: 1px solid var(--line);
  padding-left: 2rem;
}
@media (max-width: 720px) {
  .roi-block {
    text-align: left;
    border-left: none;
    border-top: 1px solid var(--line);
    padding-left: 0;
    padding-top: 1.2rem;
  }
}
.roi-block .label {
  color: var(--muted);
  font-size: 0.85rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.roi-value {
  font-family: "Bebas Neue", sans-serif;
  font-size: clamp(2.8rem, 8vw, 4.5rem);
  color: var(--gold);
  line-height: 1;
}
.scroll-hint {
  margin-top: 3rem;
  color: var(--muted);
  font-size: 0.8rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  opacity: 0.7;
  animation: pulse 2.4s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 0.9; }
}

section {
  padding: 3.2rem 0 1rem;
  border-top: 1px solid var(--line);
  animation: rise 0.8s ease-out both;
}
section:nth-of-type(1) { animation-delay: 0.05s; }
section:nth-of-type(2) { animation-delay: 0.1s; }
section:nth-of-type(3) { animation-delay: 0.15s; }
section:nth-of-type(4) { animation-delay: 0.2s; }
.sec-title {
  font-family: "Bebas Neue", sans-serif;
  font-size: 1.85rem;
  color: var(--fog);
  letter-spacing: 0.06em;
  margin-bottom: 0.35rem;
}
.sec-sub {
  color: var(--muted);
  font-size: 0.95rem;
  margin-bottom: 1.8rem;
}

/* Basics strip — no cards */
.stats-strip {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 1.2rem 1rem;
}
@media (max-width: 800px) {
  .stats-strip { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 420px) {
  .stats-strip { grid-template-columns: 1fr; }
}
.stat .k {
  display: block;
  color: var(--muted);
  font-size: 0.78rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.stat .v {
  font-family: "Bebas Neue", sans-serif;
  font-size: 2.35rem;
  color: var(--text);
  line-height: 1.1;
  margin-top: 0.15rem;
}
.stat .v.win { color: var(--profit); }
.stat .v.lose { color: var(--loss); }
.stat .v.refund { color: var(--refund); }

/* Outcome donut */
.outcome-grid {
  display: grid;
  grid-template-columns: minmax(220px, 280px) 1fr;
  gap: 2.5rem;
  align-items: center;
}
@media (max-width: 720px) {
  .outcome-grid { grid-template-columns: 1fr; justify-items: center; }
}
.donut-wrap { position: relative; width: 240px; height: 240px; }
.donut-wrap svg { width: 100%; height: 100%; transform: rotate(-90deg); }
.donut-center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}
.donut-center .rate {
  font-family: "Bebas Neue", sans-serif;
  font-size: 2.8rem;
  color: var(--gold);
  line-height: 1;
}
.donut-center .rate-label {
  color: var(--muted);
  font-size: 0.75rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.legend { list-style: none; display: flex; flex-direction: column; gap: 0.7rem; width: 100%; }
.legend li {
  display: grid;
  grid-template-columns: 12px 1fr auto auto;
  gap: 0.75rem;
  align-items: center;
  font-size: 0.95rem;
}
.swatch { width: 12px; height: 12px; border-radius: 2px; }
.legend .name { color: var(--fog); }
.legend .n { font-family: "Bebas Neue", sans-serif; font-size: 1.35rem; color: var(--text); }
.legend .pct { color: var(--muted); font-size: 0.85rem; min-width: 3.2rem; text-align: right; }

/* Capital meters */
.meters { display: flex; flex-direction: column; gap: 1.35rem; }
.meter-row { display: grid; grid-template-columns: 7.5rem 1fr auto; gap: 1rem; align-items: center; }
@media (max-width: 560px) {
  .meter-row { grid-template-columns: 1fr; gap: 0.35rem; }
}
.meter-label { color: var(--fog); font-size: 0.92rem; }
.meter-track {
  height: 10px;
  background: rgba(255,255,255,0.08);
  border-radius: 999px;
  overflow: hidden;
}
.meter-fill {
  height: 100%;
  width: 0;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--pitch-mid), var(--gold));
  transition: width 1.1s cubic-bezier(0.22, 1, 0.36, 1);
}
.meter-fill.util { background: linear-gradient(90deg, #2a6b45, #8bc34a); }
.meter-fill.yield { background: linear-gradient(90deg, #1a5c3a, var(--profit)); }
.meter-val {
  font-family: "Bebas Neue", sans-serif;
  font-size: 1.55rem;
  color: var(--gold);
  min-width: 4.5rem;
  text-align: right;
}
.meter-note {
  margin-top: 1.2rem;
  color: var(--muted);
  font-size: 0.88rem;
}

/* Market bars */
.market-list { display: flex; flex-direction: column; gap: 1.6rem; }
.market-item .head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 0.45rem;
  gap: 1rem;
}
.market-item .name {
  font-family: "Bebas Neue", sans-serif;
  font-size: 1.45rem;
  color: var(--fog);
}
.market-item .meta { color: var(--muted); font-size: 0.88rem; }
.bar-pair { display: grid; gap: 0.45rem; }
.bar-line {
  display: grid;
  grid-template-columns: 3.2rem 1fr auto;
  gap: 0.65rem;
  align-items: center;
  font-size: 0.82rem;
  color: var(--muted);
}
.bar-track {
  height: 8px;
  background: rgba(255,255,255,0.08);
  border-radius: 999px;
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  width: 0;
  border-radius: 999px;
  transition: width 1.1s cubic-bezier(0.22, 1, 0.36, 1);
}
.bar-fill.stake { background: #4a8f66; }
.bar-fill.pnl-pos { background: var(--profit); }
.bar-fill.pnl-neg { background: var(--loss); }
.bar-num {
  font-family: "Bebas Neue", sans-serif;
  font-size: 1.15rem;
  color: var(--text);
  min-width: 4.8rem;
  text-align: right;
}
.footer {
  margin-top: 3.5rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: 0.8rem;
}
</style>
</head>
<body>
  <div class="wrap">
    <header class="hero">
      <div class="brand">World Cup Book</div>
      <p class="tagline">2026 世界杯期间的真实账本——以固定本金滚动，看清周转、占用与最终回报。</p>
      <p class="period" id="period"></p>
      <div class="hero-numbers">
        <div class="pnl-block">
          <div class="label">最终净盈利</div>
          <div class="pnl-value" id="pnlValue">+0</div>
          <p class="bankroll-flow" id="bankrollFlow"></p>
        </div>
        <div class="roi-block">
          <div class="label">ROI · 相对本金</div>
          <div class="roi-value" id="roiValue">0%</div>
        </div>
      </div>
      <p class="scroll-hint">Scroll</p>
    </header>

    <section>
      <h2 class="sec-title">基础统计</h2>
      <p class="sec-sub">场次结构与资金流水</p>
      <div class="stats-strip" id="statsStrip"></div>
    </section>

    <section>
      <h2 class="sec-title">结算构成</h2>
      <p class="sec-sub">赢 / 半赢 / 退还 / 半输 / 输</p>
      <div class="outcome-grid">
        <div class="donut-wrap">
          <svg viewBox="0 0 120 120" id="donut" aria-hidden="true"></svg>
          <div class="donut-center">
            <div class="rate" id="winRate">—</div>
            <div class="rate-label">胜率</div>
          </div>
        </div>
        <ul class="legend" id="legend"></ul>
      </div>
    </section>

    <section>
      <h2 class="sec-title">资金效率</h2>
      <p class="sec-sub">周转、占用与流水收益</p>
      <div class="meters" id="meters"></div>
      <p class="meter-note" id="peakNote"></p>
    </section>

    <section>
      <h2 class="sec-title">盘口拆分</h2>
      <p class="sec-sub">投注额与盈亏对比</p>
      <div class="market-list" id="markets"></div>
    </section>

    <p class="footer" id="footer"></p>
  </div>

<script>
const DATA = __DATA_JSON__;

const STATUS_META = [
  { key: "WIN", label: "全赢", color: "#3ecf7a" },
  { key: "WIN_HALF", label: "半赢", color: "#8bc34a" },
  { key: "DRAW", label: "退还", color: "#6b8f71" },
  { key: "LOSE_HALF", label: "半输", color: "#d4a017" },
  { key: "LOSE", label: "全输", color: "#c44b3c" },
];

function fmtMoney(n, signed = false) {
  const abs = Math.abs(n).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (!signed) return abs;
  return (n >= 0 ? "+" : "-") + abs;
}

function animateNumber(el, target, { signed = false, suffix = "", decimals = 2, duration = 1100 } = {}) {
  const start = performance.now();
  const from = 0;
  function frame(now) {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - t, 3);
    const val = from + (target - from) * eased;
    let text;
    if (decimals === 0) {
      text = Math.round(val).toLocaleString("zh-CN");
      if (signed) text = (val >= 0 ? "+" : "") + text.replace(/^-/, "");
      if (signed && target < 0) text = "-" + Math.round(Math.abs(val)).toLocaleString("zh-CN");
    } else {
      text = fmtMoney(val, signed);
    }
    el.textContent = text + suffix;
    if (t < 1) requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

function renderHero() {
  const a = DATA.amounts;
  const m = DATA.metrics;
  const p = DATA.period;
  document.getElementById("period").textContent =
    `${p.first_kickoff}  →  ${p.last_kickoff}  ·  ${p.active_days} 个开赛日`;

  const pnlEl = document.getElementById("pnlValue");
  if (a.total_pnl < 0) pnlEl.classList.add("neg");
  animateNumber(pnlEl, a.total_pnl, { signed: true, decimals: 2 });

  document.getElementById("bankrollFlow").innerHTML =
    `本金 <strong>${fmtMoney(DATA.capital)}</strong> → 期末 <strong>${fmtMoney(a.ending_bankroll)}</strong>`;

  const roiEl = document.getElementById("roiValue");
  animateNumber(roiEl, m.roi * 100, { signed: true, suffix: "%", decimals: 2 });
}

function renderStats() {
  const c = DATA.counts;
  const a = DATA.amounts;
  const items = [
    { k: "投注场次", v: String(c.bets), cls: "" },
    { k: "赢（含半赢）", v: String(c.win), cls: "win" },
    { k: "亏（含半输）", v: String(c.lose), cls: "lose" },
    { k: "退还", v: String(c.refund), cls: "refund" },
    { k: "总投注金额", v: fmtMoney(a.total_stake), cls: "" },
  ];
  document.getElementById("statsStrip").innerHTML = items.map(it => `
    <div class="stat">
      <span class="k">${it.k}</span>
      <div class="v ${it.cls}">${it.v}</div>
    </div>
  `).join("");
}

function renderDonut() {
  const status = DATA.counts.by_status;
  const total = DATA.counts.bets;
  const r = 42;
  const c = 2 * Math.PI * r;
  let offset = 0;
  const parts = STATUS_META.map(s => {
    const n = status[s.key] || 0;
    const len = total ? (n / total) * c : 0;
    const seg = { ...s, n, len, offset };
    offset += len;
    return seg;
  });

  const svg = document.getElementById("donut");
  svg.innerHTML = parts.map(p => `
    <circle cx="60" cy="60" r="${r}" fill="none"
      stroke="${p.color}" stroke-width="14"
      stroke-dasharray="${p.len} ${c - p.len}"
      stroke-dashoffset="${-p.offset}"
      opacity="0.92"></circle>
  `).join("") + `<circle cx="60" cy="60" r="28" fill="#06140c" opacity="0.55"></circle>`;

  document.getElementById("winRate").textContent =
    (DATA.counts.win_rate * 100).toFixed(1) + "%";

  document.getElementById("legend").innerHTML = parts.map(p => `
    <li>
      <span class="swatch" style="background:${p.color}"></span>
      <span class="name">${p.label} · ${p.key}</span>
      <span class="n">${p.n}</span>
      <span class="pct">${total ? ((p.n / total) * 100).toFixed(1) : 0}%</span>
    </li>
  `).join("");
}

function renderMeters() {
  const m = DATA.metrics;
  // Normalize bars: turnover against 10x ceiling; rates against 100%
  const rows = [
    { label: "资金周转率", valueText: m.turnover_rate.toFixed(2) + "x", pct: Math.min(100, (m.turnover_rate / 10) * 100), cls: "" },
    { label: "使用率 · 峰值", valueText: (m.utilization_peak * 100).toFixed(1) + "%", pct: m.utilization_peak * 100, cls: "util" },
    { label: "使用率 · 均值", valueText: (m.utilization_avg * 100).toFixed(1) + "%", pct: Math.min(100, m.utilization_avg * 100 * 4), cls: "util", raw: m.utilization_avg },
    { label: "Yield · 流水", valueText: (m.yield * 100).toFixed(2) + "%", pct: Math.min(100, Math.max(0, m.yield * 100 * 4)), cls: "yield" },
  ];
  document.getElementById("meters").innerHTML = rows.map((r, i) => `
    <div class="meter-row">
      <div class="meter-label">${r.label}</div>
      <div class="meter-track"><div class="meter-fill ${r.cls}" data-pct="${r.pct}" id="meter${i}"></div></div>
      <div class="meter-val">${r.valueText}</div>
    </div>
  `).join("");

  document.getElementById("peakNote").textContent =
    `峰值日 ${m.peak_day}：占用 ${fmtMoney(m.peak_day_exposure)} 元 / ${m.peak_day_bets} 笔 · ROI ${(m.roi * 100).toFixed(2)}%`;

  requestAnimationFrame(() => {
    document.querySelectorAll(".meter-fill").forEach(el => {
      el.style.width = el.dataset.pct + "%";
    });
  });
}

function renderMarkets() {
  const markets = Object.entries(DATA.by_market);
  const maxStake = Math.max(...markets.map(([, v]) => v.stake), 1);
  const maxPnlAbs = Math.max(...markets.map(([, v]) => Math.abs(v.pnl)), 1);

  document.getElementById("markets").innerHTML = markets.map(([name, row]) => {
    const stakePct = (row.stake / maxStake) * 100;
    const pnlPct = (Math.abs(row.pnl) / maxPnlAbs) * 100;
    const pnlCls = row.pnl >= 0 ? "pnl-pos" : "pnl-neg";
    return `
      <div class="market-item">
        <div class="head">
          <span class="name">${name}</span>
          <span class="meta">${row.n} 场 · Yield ${(row.roi_on_stake * 100).toFixed(2)}%</span>
        </div>
        <div class="bar-pair">
          <div class="bar-line">
            <span>投注</span>
            <div class="bar-track"><div class="bar-fill stake" data-pct="${stakePct}"></div></div>
            <span class="bar-num">${fmtMoney(row.stake)}</span>
          </div>
          <div class="bar-line">
            <span>盈亏</span>
            <div class="bar-track"><div class="bar-fill ${pnlCls}" data-pct="${pnlPct}"></div></div>
            <span class="bar-num">${fmtMoney(row.pnl, true)}</span>
          </div>
        </div>
      </div>
    `;
  }).join("");

  requestAnimationFrame(() => {
    document.querySelectorAll(".bar-fill").forEach(el => {
      el.style.width = el.dataset.pct + "%";
    });
  });
}

function renderFooter() {
  document.getElementById("footer").textContent =
    `生成于 ${DATA.generated_at} · 数据来自 betting_history.csv · 由 analyze_betting_history.py 同步产出`;
}

renderHero();
renderStats();
renderDonut();
renderMeters();
renderMarkets();
renderFooter();
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="分析世界杯投注记录")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--capital", type=float, default=1200.0)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--html", type=Path, default=DEFAULT_HTML)
    args = parser.parse_args()

    bets = load_bets(args.csv)
    result = analyze(bets, args.capital)
    report = render_report(result)
    html = render_html(result)

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")
    args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.html.write_text(html, encoding="utf-8")

    print(report)
    print(f"\n已写入: {args.report}")
    print(f"已写入: {args.json}")
    print(f"已写入: {args.html}")


if __name__ == "__main__":
    main()
