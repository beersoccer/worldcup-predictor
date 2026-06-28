# worldcup-predictor 使用指南

本文档面向日常使用者，覆盖环境搭建、每日操作流程、下注建议的解读方式、
底层模型原理，以及所有 CLI 参数的完整说明。

---

## 1. 环境搭建

```bash
# 克隆仓库
git clone https://github.com/beersoccer/worldcup-predictor.git
cd worldcup-predictor

# 创建 Python 3.11 虚拟环境并激活
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置 API 密钥（仅免费 key 是必须的）
cp .env.example .env
```

`.env` 中的关键字段：

| 变量 | 是否必须 | 说明 |
|---|---|---|
| `FOOTBALLDATA_KEY` | 必须（免费） | football-data.org 赛程/比分，注册即得 |
| `APIFOOTBALL_KEY` | 可选（免费） | API-Football 首发阵容，注册即得 |
| `ODDS_API_KEY` | 可选（付费） | The Odds API，含 Pinnacle 盘口，约 $30/月 |

**所有命令都需要** `PYTHONPATH=.` 前缀和激活的 venv。

---

## 2. 每日操作流程

### 2.1 标准流程（比赛日）

```bash
# Step 1：赛前下午 — 拉取全量数据
source .venv/bin/activate
PYTHONPATH=. python -m skill.helpers.cli fetch --all

# Step 2：生成预测（含 50k 蒙特卡洛模拟）
PYTHONPATH=. python -m skill.helpers.cli predict --simulate

# Step 3：查看今日推荐下注（默认 1X2 胜负平，Run 31 验证最稳健）
PYTHONPATH=. python -m skill.helpers.cli bet --bankroll 1500

# Step 4（可选）：发布到本地看板
PYTHONPATH=. python -m skill.helpers.cli publish
python -m http.server 8780 --directory site   # 浏览器打开 http://localhost:8780

# Step 5：赛前 30 分钟再次更新（获取最新 Polymarket 价格 + 确认首发）
PYTHONPATH=. python -m skill.helpers.cli fetch --all
PYTHONPATH=. python -m skill.helpers.cli bet --bankroll 1500

# 跨时区提前准备：今晚提前为明日生成预测和下注建议
# --date 的作用：以 2026-06-23 为 DC 模型截止日（as_of），结果写入 reports/2026-06-23/
# predict 预测所有未完赛场次；bet --date 只从该目录取 date==2026-06-23 的比赛
PYTHONPATH=. python -m skill.helpers.cli predict --simulate --date 2026-06-23
PYTHONPATH=. python -m skill.helpers.cli bet --bankroll 1500 --date 2026-06-23
```

### 2.2 赛后结算（次日）

```bash
# 一条命令完成所有工作：回填结果 + 重预测 + 重发布看板
PYTHONPATH=. python -m skill.helpers.cli review
```

`review` 内部依次执行：拉取最新比分 → 结算已完赛注单 → 重新跑 `predict --simulate` → 重新跑 `publish`。**不需要**再单独执行 `predict` 或 `publish`。

---

## 3. bet 命令详解

### 3.1 基本语法

```bash
PYTHONPATH=. python -m skill.helpers.cli bet [选项]
```

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--bankroll` | 10000 | 当前本金（任意单位，输出 stake 与之成比例） |
| `--mode` | `1x2` | 推荐市场，见下表 |
| `--date` | 今日 | 指定预测日期，格式 `YYYY-MM-DD` |
| `--edge` | 0.06 | 最低 edge 门槛，低于此不输出；可临时调低观察更多候选 |
| `--max-bets` | 无限制 | 设置后只输出 edge 最高的 N 条，不设则显示全部超过门槛的注单 |
| `--best-line` | 关闭 | 启用后每场每类市场只保留 edge 最高的一条（防相关嵌套下注），默认关闭 |

### 3.2 五种模式对比

| 模式 | 命令 | 输出 | 适用场景 |
|---|---|---|---|
| `1x2`（默认） | `bet --mode 1x2` | 胜平负 | 推荐日常使用（Run 31 实盘验证，命中率 56%，ROI +14.7%） |
| `ah` | `bet --mode ah` | 让球盘 3 条线 | 仅看让球盘 |
| `ou` | `bet --mode ou` | 大小盘 3 条线 | 仅看大小盘 |
| `ahou` | `bet --mode ahou` | 让球盘 + 大小盘各 3 条线 | 对齐主流亚洲盘口（赔率为模型公允价，非真实市场赔率） |
| `all` | `bet --mode all` | 1X2 + AH + OU 全部 | Kelly 在所有市场间统一分配仓位 |

**自动选线规则**（动态、按比赛而异）：

- **让球盘主线** = `round-to-half(-(λ_h - λ_a))`，再叠加 ±0.5 形成 3 条线
  - 例：FRA(λ=1.65) vs MAR(λ=0.88)，差 0.77 → 主线 -1.0，3 条线 = [-1.5, -1.0, -0.5]
- **大小盘主线** = `round-to-half(λ_h + λ_a)`，再叠加 ±0.5
  - 例：总进球 2.53 → 主线 2.5，3 条线 = [2.0, 2.5, 3.0]
- 让球盘范围 [-3, +3]，大小盘范围 [1.5, 4.5]，超出截断

### 3.3 输出解读

```
Bet                                                            p_win   odds    edge     stake
FRA vs MAR · AH -0.5 home                                     0.623   1.847   8.3%    415.00
FRA vs MAR · OU 2.5 under                                      0.541   2.100   6.1%    210.00

ARG vs MEX · AH +0.5 home                                     0.712   1.680   5.1%    195.00

─────────────────────────────────────────────────────────────────────────────────────────────
TOTAL                                                                                  820.00

logged → reports/bets/2026-06-20.json
```

各字段含义：

| 字段 | 含义 |
|---|---|
| `Bet` | 比赛 · 市场类型 · 方向（home/away/draw） |
| `p_win` | 模型估算的赢盘概率（DC + 上下文层 + 市场锚定） |
| `odds` | 市场隐含赔率（1 / 市场隐含概率，无佣金） |
| `edge` | 模型概率 − 市场隐含概率；≥ 6% 才会进入建议（默认，可用 `--edge` 覆盖，见 §5.1） |
| `stake` | 建议押注金额（按 1/4 Kelly 计算，已受单注 5% 上限约束） |

**排序规则：** 输出按场次分组，场次之间以空行分隔；场次按**该场最高 edge 降序**排列（最有价值的比赛在最前）；同场次内按 edge 降序排列。

**AH 方向解读：**
- `AH -0.5 home`：押主队赢（需赢至少 1 球）
- `AH +0.5 home`：押主队不输（赢或平均可）
- `AH -0.5 away` / `AH +0.5 away`：客队方向，反之亦然

---

## 4. 底层模型原理

### 4.0 设计哲学：市场锚定的集成模型

**博彩公司的共识赔率长期来看很难被打败**——它聚合了全球聪明钱、内幕信息、
临场调整等所有公开和半公开信息。但**盲目复制赔率没有 edge**：照抄市场只能
拿到博彩公司收佣后的负期望。

本项目的设计是**市场锚定的集成（market-anchored ensemble）**：

1. **以去佣后的市场共识作为强先验**：Polymarket、Kalshi 多源平均归一
2. **叠加独立信号层**：Dixon-Coles 双变量泊松、ELO 强度先验、
   情境调整（海拔、休息日、伤病、跨洲强度差）
3. **混合输出**：`P_final = 0.60·P_market + 0.40·P_model_adj`
4. **关注分歧而非一致**：模型与市场**意见相同时**没有 edge，**意见相左时**
   才是值得下注的信号

这个哲学决定了所有下游设计：每个新因子必须在 walk-forward 上**独立打败基线**
才能进入模型；所有市场（1X2 / AH / OU 各线）必须通过 walk-forward 校准才能
进入下注白名单（见 §9）。

### 4.1 第一层：Dixon-Coles 期望进球

模型从 49,000+ 场历史国际比赛中拟合每支球队的**进攻力 α** 和**防守力 β**，
预测主客队各自的期望进球（λ_home、λ_away）：

```
λ_home = exp(α_home − β_away + home_advantage)
λ_away = exp(α_away − β_home)
```

加入 Dixon-Coles 低分修正（ρ 参数，避免 0-0/1-0/0-1/1-1 系统性低估），
和指数时间衰减（ξ=0.001，最近比赛权重更高）。训练窗口：截至预测日前 3 年。

有了 λ_home 和 λ_away，把每个可能的比分（0-0 到 10-10）的概率全部算出来，
组成一张 **11×11 的得分矩阵**，这是所有下游计算的基础。

### 4.2 第二层：强度调整

三个可选增强器，各以 10% 权重（`TALENT_WEIGHT`）叠入：

| 模块 | 数据源 | 说明 |
|---|---|---|
| `talent.py` | ClubElo.com | 俱乐部 ELO 均值 → 国家队进攻/防守强度 |
| `fcratings.py` | EA FC25 球员评分 | OVR + 攻防分项 → 强度先验 |
| `injuries.py` | `data/injuries_wc2026.json`（静态先验）+ API-Football `/injuries`（预测日实时拉取，自动合并） | 赛前缺阵球员从阵容移除后重算强度 |

**跨联合会修正**（Run 28）：UEFA/CONMEBOL 与其他联合会对阵时，
主流模型系统性低估强队优势 → 对强队 λ 乘以 `exp(+0.075)`（gap=0.15）。

### 4.3 第三层：比赛情境层

对 λ_home / λ_away 施加场景乘数：

| 因素 | 状态 | 说明 |
|---|---|---|
| 海拔 | ✅ 采用 | 主场海拔 >2000m → 客队 λ 下调 |
| 休息日差 | ✅ 采用（Run 12） | 多休 1 天 → 己方 λ +约 2% |
| 天气 | ❌ 拒绝（Run 19/20） | 1642 场回测无显著信号 |
| 其他 10 项 | ❌ 全部拒绝 | 重要性、死橡皮、卫冕冠军等均无信号 |

### 4.4 第四层：市场锚定集成

```
P_final = 0.60 × P_market + 0.40 × P_model_adj
```

- `P_market`：Polymarket + Kalshi + The Odds API（若有 key）多源平均、去佣归一
- `P_model_adj`：DC + 强度 + 情境的综合模型概率
- 权重 `MARKET_WEIGHT=0.60` 经 Run 26 walk-forward 验证

### 4.5 让球盘 / 大小盘的 edge 来源（业界标准做法）

参考 Pinnacle 与学术文献，欧赔（1X2）转亚盘（AH/OU）的标准做法是
**反解市场隐含的进球期望 (λ_h^M, λ_a^M)**：

**步骤：**
1. 已知 DC 模型给出 `(λ_h^DC, λ_a^DC, ρ)` → 通过得分矩阵输出 1X2
2. **保持 ρ 不变**（ρ 是联赛级低分修正，不是单场参数），用 L-BFGS-B 反解
   `(λ_h^M, λ_a^M)`，使其经 DC 得分矩阵后输出**与市场 1X2 完全一致**
3. 用反解的市场 λ 通过同一套 `asian_handicap()` / `over_under()` 函数，
   计算**任意 AH/OU 线**的市场隐含概率
4. `edge = DC概率 − 市场λ概率`，所有线条统一比较

**优势：**
- 保留 DC 的 ρ 低分修正，不像粗暴的 Skellam 假设独立 Poisson
- 一次反解，所有 AH/OU 线（±0.5、±1、±1.5、±2、±2.5、OU 2/2.5/3/3.5/4）都可算 edge
- 与 Pinnacle 的"1X2 + AH + OU 内部一致定价"逻辑同源

**白名单约束（Run 27 + Run 30 验证）：**
- **OU 1.5**：Run 27 实证拒绝（Brier 劣于基线），硬封锁
- **OU 2.0**：Run 30 实证拒绝（Δ Brier +0.030，反技能），硬封锁——与 OU 1.5 同属 DC ρ 低分修正区，模型在此段系统性失准
- **AH −2.5 到 +2.5（含所有整数线）**：Run 30（2018-2024，n=419-574/线）全部 beat 基线，正式验证
- **OU 2.5 到 4.5**：Run 27 + Run 30 验证通过（OU 2.5 低置信度）
- **选线规则**：每场每类市场（AH / OU 分别）只推送 edge 最高的一条线进入 Kelly 引擎，避免同一方向的嵌套押注

### 4.6 罚点球：公平硬币（Run 29）

淘汰赛点球大战使用 **50/50 硬币**，不使用强度加权。
Walk-forward 在 231 场实际点球上证明：强度加权方案 Brier=0.2683，
硬币 Brier=0.2500，前者反技能。在可用样本量下无法恢复球队级点球技能。

---

## 5. 凯利公式与资金管理

### 5.1 参数设置

| 参数 | 值 | 说明 |
|---|---|---|
| Kelly 分数 | 1/4（25%） | 全 Kelly 风险太大，缩为 1/4 保守执行 |
| 单注上限 | 本金 5% | 防止单笔大赌 |
| 总仓位上限 | 本金 30% | 同日多注合并不超过 30% |
| Edge 门槛 | 6%（默认） | 无真实 Pinnacle 盘口时的保守值；可用 `--edge` 覆盖 |
| 每日注数上限 | 10（默认） | 按 edge 降序保留最优 N 条；可用 `--max-bets` 覆盖 |
| 最小注额 | 本金 0.5% | 信号太弱的注单丢弃 |

### 5.2 下注金额计算详解

每笔注单的 stake 经过四步流水线（代码：`skill/bet/kelly.py:portfolio_kelly`）：

**第一步：全 Kelly 公式**

```
f* = (b·p − q) / b
其中 b = decimal_odds − 1，q = 1 − p_win
```

**第二步：缩为 1/4 Kelly**

```
f = f* × 0.25
```

1/4 Kelly 的意义：模型概率是估计值，不是真值。理论研究表明，当概率估计偏高 x%，
full Kelly 会造成约 2x% 的额外回撤；缩为 1/4 是在误差保护与增长率之间取的保守平衡点。

**具体数值例子：**

| 参数 | 值 |
|---|---|
| p_win（模型） | 0.623 |
| decimal_odds | 1.847 |
| b = 1.847−1 | 0.847 |
| full Kelly f* | (0.847×0.623 − 0.377) / 0.847 = **17.8%** |
| 1/4 Kelly f | 17.8% × 0.25 = **4.45%** |
| 单注上限 | 5%（未触发） |
| stake（本金 1500） | **66.75** |

**第三步：三道截断**

1. `f = min(f, 5%)` — 单注上限，防止单注过大
2. `f < 0.5%` 则丢弃 — 信号太弱，噪音大于期望
3. 所有同日注单 kelly_fraction 之和 > 30% → 等比例缩减至 30%

**第四步：`stake = bankroll × kelly_fraction`**

### 5.3 AH / OU / 1X2 盘口结算机制

盘口结算在 `skill/helpers/cli.py:_betting_payload` 中按真实比分精确计算，逻辑如下：

**1X2（胜平负）**
```
actual = "home" | "draw" | "away"（按真实比分）
won = (side == actual)
payout = stake × (odds − 1)   # 赢
payout = −stake                # 输
```

**AH（让球盘）**
```
adjusted = (home_score − away_score) + line

side == "home": won = adjusted > 0，push = adjusted == 0
side == "away": won = adjusted < 0，push = adjusted == 0

push（仅整数线才出现，半球线不可能走水）：payout = 0（退本金）
赢：payout = stake × (odds − 1)
输：payout = −stake
```

**OU（大小盘）**
```
total = home_score + away_score

push = (total == line)   # 仅整数线可走水
over_wins = total > line
won = over_wins（买大）或 not over_wins（买小）
push：payout = 0；赢：payout = stake × (odds − 1)；输：payout = −stake
```

### 5.4 ROI 与看板 P&L 的局限性

**ROI 计算：**
```
ROI = total_pnl / total_stake
```
逐日按真实比分结算，累计。

**重要局限：当前 AH/OU 赔率是模型公允价，不是真实市场赔率。**

原因：Pinnacle 历史 AH/OU 存档需 The Odds API Business 档（~$99/月），
尚未接入（P0.2b 待办）。因此：

- 看板显示的 AH/OU P&L 是"若以模型公允价成交"的模拟盈亏，**非真实市场 ROI**
- 真实 edge 可能低于模型估算（市场在 AH/OU 上通常比 1X2 更有效）
- 接入 Pinnacle 实盘后，ROI 才具备真实参考价值

### 5.5 仓位翻倍分析（1/4 Kelly → 1/2 Kelly）

| 指标 | 1/4 Kelly（当前） | 1/2 Kelly（翻倍） |
|---|---|---|
| 期望增长率（相对全 Kelly） | ~75% | ~87.5% |
| 理论破产概率 | ≈0 | ≈0（分数≤1 时均安全） |
| 预期最大回撤 | ~15–20% | ~30–40% |
| 参数误差放大 | 最小 | 中等 |
| 单注上限 | 5% | 需同步升至 10%（否则截断抵消翻倍） |
| 总仓位上限 | 30% | 需同步升至 60% |

**结论：在当前阶段维持 1/4 Kelly。**

翻倍的前提条件尚不满足：
1. **AH/OU 赔率来自模型公允价，不是真实 Pinnacle 盘口。** 真实 edge 未知，基于虚高 edge 放大仓位会成倍放大风险。
2. **实盘验证样本不足。** 研究文献建议"20+ 注实证 edge ≥ 5% 后，可考虑升至 1/3 Kelly"。翻到 1/2 Kelly 需要更大样本。

**合理升级路径：** 接入 Pinnacle 真实 AH/OU 赔率（P0.2b）并积累 30+ 注实证数据后，
若真实 ROI ≥ 5%，可将 Kelly 分数从 1/4 升至 1/3，同步将单注上限从 5% 升至 7%。

### 5.6 建议执行原则

1. **严格按 stake 执行**，不因"手感"加减仓
2. **赛前 30 分钟最后一次 `fetch`**，确保 Polymarket 价格是最新的
3. 整个世界杯约产生 20–30 注（edge 达标），每注约占本金 2–4%
4. 短期方差是正常的，即使模型有 5% edge，也可能连续 5 场亏损
5. **优先使用 1X2 盘口**（Run 31 实盘验证）。小组赛 36 场实盘数据显示：1X2 命中率 56%、ROI +14.7%；AH 场次命中率仅 21%、ROI −27%，且存在强弱队悬殊场次的系统性偏差。接入 Pinnacle 真实 AH/OU 赔率（P0.2b）前，以 `--mode 1x2` 或 `--mode all` 为主，AH/OU 仅作参考。

---

## 6. 完整 CLI 参考

```bash
PYTHONPATH=. python -m skill.helpers.cli <subcommand> [args]
```

| 子命令 | 参数 | 用途 |
|---|---|---|
| `fetch --all` | — | 拉取历史结果、赛程、阵容、赔率、天气、首发 |
| `predict --simulate` | `--sims N`（默认 50000），`--date YYYY-MM-DD` | 预测全部未完赛场次 + 蒙特卡洛锦标赛模拟；已完赛场次自动跳过 |
| `predict --match wc2026-000` | — | 单场预测（调试用） |
| `publish [--date]` | — | 打包报告 → `site/data.json` |
| `review` | `--sims N` | 赛后结算：补充结果、重预测、更新 P&L |
| `market [--date]` | — | 打印夺冠赔率：模型 vs Polymarket + edge |
| `bet --bankroll N` | `--mode [ah\|ou\|ahou\|1x2\|all]`（默认 `1x2`），`--date`，`--edge`（默认 0.06），`--max-bets N`，`--best-line` | 生成今日下注建议 |
| `players --match <id>` | `--refresh` | 每场比赛可能进球的球员列表 |
| `portraits [--topk N]` | — | 预下载球员头像到 `site/portraits/` |
| `backtest` | `--start`，`--end`，`--xi`，`--markets` | Walk-forward 回测（1X2 或 AH/OU） |

---

## 7. 输出文件说明

| 文件 | 生成命令 | 内容 |
|---|---|---|
| `reports/YYYY-MM-DD/predictions.json` | `predict` | 每场比赛的概率、λ、AH/OU 公允赔率 |
| `reports/YYYY-MM-DD/simulation.json` | `predict --simulate` | 蒙特卡洛夺冠概率、各轮晋级率 |
| `reports/YYYY-MM-DD/bracket.json` | `predict --simulate` | 最大概率单链赛程预测 |
| `reports/bets/YYYY-MM-DD.json` | `bet` | 当日下注建议（含 Kelly 参数、edge） |
| `site/data.json` | `publish` | 看板全量数据（预测 + 模拟 + 下注面板） |
| `reports/backtests/backtest_*.json` | `backtest` | Walk-forward 回测结果 |

---

## 8. 数据来源

### 8.1 已使用（全部免费）

| 数据 | 来源 | 用途 | API key |
|---|---|---|---|
| 历史比赛结果 + WC2026 赛程 | [martj42/international_results](https://github.com/martj42/international_results)（公共 CSV） | DC MLE 训练（49k+ 场，含友谊赛 / 资格赛 / 正赛） | 无需 |
| 进球记录 | martj42/goalscorers.csv | Golden Boot + 球员形态 | 无需 |
| 点球大战历史 | martj42/shootouts.csv | 点球硬币校准（Run 29） | 无需 |
| 赛程 / 实时比分 | football-data.org 免费层 | 比分回填 + 元信息 | `FOOTBALLDATA_KEY` |
| 比赛日首发 XI | API-Football 免费层 | 阵容确认、缺阵球员调整 | `APIFOOTBALL_KEY` |
| 预测市场（1X2） | Polymarket Gamma API + Kalshi | 市场锚定（per-match 1X2） | 无需 |
| 球场 / 海拔 / 坐标 | `data/venues_wc2026.json`（自建静态表） | 海拔上下文调整 | 无需 |
| 天气（仅展示） | Open-Meteo | 看板展示（已被 Run 19/20 证伪不作为预测因子） | 无需 |
| 俱乐部 ELO | clubelo.com（主）/ xgabora GitHub 镜像（备用） | 球员俱乐部强度 → 国家队 talent prior；主源 503 时自动切换镜像 | 无需 |
| EA FC25 球员评分 | 公开数据集（OVR + 攻防分项） | 攻防分离 talent prior | 无需 |
| 联合会归属 | `data/confederations.json` | 跨洲强度修正（Run 28） | 无需 |
| 伤病 / 缺阵 | `data/injuries_wc2026.json`（静态先验，手工维护）+ API-Football `/injuries`（每次 `predict` 自动拉取当日伤病报告并合并） | 阵容剔除后重算强度 | `APIFOOTBALL_KEY`（可选） |

### 8.2 可选付费升级

| 数据 | 来源 | 用途 | 费用 | API key |
|---|---|---|---|---|
| Pinnacle 实时 1X2 / AH / OU | The Odds API 基础付费档（`bookmakers=pinnacle`） | 让球盘 / 大小盘的实盘市场锚定 + 真实 ROI | ~$30/月 | `ODDS_API_KEY` |
| Pinnacle 历史 AH/OU 存档 | The Odds API Business 档 | 让球盘 / 大小盘的历史真实 ROI 回测 | ~$99/月 | 同上 |

详见 §11 付费升级决策。

### 8.3 已评估并拒绝的源

- **Macau / 澳彩 / 亚洲零售盘**：散户资金驱动，与 Pinnacle 高度相关但带噪更多；
  无免费 API；ToS 灰色地带，无法 walk-forward 验证
- **Transfermarkt 转会身价**：bot-protected，免费层不可大规模抓取
- **付费 xG（Opta / StatsBomb 国家队级）**：以俱乐部足球为主，国家队覆盖率不足

---

## 9. 回测与因子验证纪律

所有预测因子必须满足：
1. **Walk-forward 验证**：用严格截止日期 T 之前的数据预测 T 之后，绝无回望
2. **必须超越基线**：打败 ELO 基线或 DC 基线，才能进入模型
3. **失败因子记录在案**：见 `reports/backtests/FINDINGS.md`

已拒绝因子（实验后放弃）：天气、气候差、重要性、死橡皮、卫冕冠军、年龄乘数、
裁判因素、贝叶斯点球技能、OU 1.5 市场、强度加权点球。

---

## 10. 常见问题

**Q: `bet` 命令输出"Slate empty"，没有推荐？**  
A: 两种原因：(1) 当日比赛无 Polymarket 报价（AH 的市场锚点来自 1X2，而 1X2 需要 Polymarket）；(2) 所有比赛的 edge 都低于门槛（默认 6%）。先跑 `fetch --all` 确认有市场数据，或用 `market` 命令检查。也可用 `--edge 0.05` 临时降低门槛观察候选注单。

**Q: 为什么默认是 `--mode 1x2`？**  
A: WC2026 小组赛 36 场实盘验证（Run 31）：1X2 场次命中率 56%、ROI +14.7%，
是三类盘口中最稳健的。AH 场次命中率仅 21%，且当前 AH/OU 赔率来自模型公允价而非真实
Pinnacle 盘口，edge 可信度有限。需要亚洲盘口时使用 `--mode ahou`。

**Q: 现在 AH ±1.5、±2.5、整数线、OU 各档都能下注吗？**  
A: 大部分可以。1X2→λ_market 反解出市场隐含的进球期望后，所有线条的市场隐含概率
都可以一致地计算。但有两条线被 walk-forward 实证拒绝（Run 27 + Run 30），永久封锁：
**OU 1.5**（Brier 劣于无技能基线）和 **OU 2.0**（Δ Brier +0.030，强反技能）。
其余 AH −2.5 到 +2.5 及 OU 2.5-4.5 均已通过 Run 30 验证。
每场每类市场（AH / OU 各自）只推送 edge 最高的一条线，避免重复押注同方向嵌套赌注。

**Q: 点球大战概率为何是 50/50？**  
A: Walk-forward 在 231 场实际点球上验证，任何基于球队强度的加权方案都比硬币更差（Run 29）。

**Q: 如何查看历史下注的盈亏？**  
A: 运行 `review` 后，看板的"Betting"面板会显示累计 P&L、ROI 和最大回撤。
或直接读 `reports/bets/` 目录下各日期的 JSON 文件。

**Q: 看板上的 AH/OU P&L 是真实盈亏吗？**  
A: **不是真实市场盈亏**，是模拟值。当前 AH/OU 赔率来自模型自算的公允价（DC 得分矩阵反解），而非 Pinnacle 实盘赔率。接入 The Odds API Pinnacle 真实盘口（P0.2b）后，P&L 才具备真实参考价值。1X2 的赔率同样来自 Polymarket/Kalshi 去佣后的公允价。详见 §5.4。

**Q: 实盘数据显示哪种盘口效果最好？**  
A: WC2026 小组赛 36 场实盘统计（Run 31，2026-06-28）：

| 盘口 | 命中率（场次） | ROI | 说明 |
|---|---|---|---|
| **1X2 胜负平** | **56%** | **+14.7%** | 使用真实 Polymarket 赔率，剔除最大赢注后仍 +9.2% |
| OU 大小盘 | 45% | +37.1% | 严重依赖单注（Algeria vs Austria OU 2.5 over，剔除后 +11.6%） |
| AH 让球盘 | 21% | −27.4% | 存在系统性偏差：强弱队悬殊场次让球线低估，多线条同时亏损放大损失 |

**当前推荐：以 `--mode 1x2` 为主**。AH 在强弱队悬殊的淘汰赛阶段风险更大；OU 可辅助但方差极高。待接入 Pinnacle 真实 AH/OU 赔率（P0.2b）后再重新评估。详见 `reports/backtests/FINDINGS.md` Run 31。

**Q: 为什么不把 Kelly 分数翻倍以提高收益？**  
A: 翻倍（1/4→1/2 Kelly）的前提是真实 edge 已验证充分。当前 AH/OU 赔率是模型公允价而非真实市场赔率，真实 edge 未知；加之实盘样本尚不足 20 注。基于未验证的 edge 放大仓位会成倍放大回撤风险。接入 Pinnacle 真实盘口并积累 30+ 注实证数据后，若 ROI ≥ 5%，可考虑升至 1/3 Kelly。详见 §5.5。

**Q: 出现 `[clubelo] primary API unavailable` 警告怎么办？**  
A: 正常现象，`api.clubelo.com` 服务器偶发宕机。系统会自动切换到 GitHub 镜像数据（895 支俱乐部，最新至 2025-06-01），talent 层仍然工作，预测结果基本不受影响。无需手动干预；等官方 API 恢复后下一次 `fetch --all` 会自动更新本地缓存。

**Q: 比赛预测是否有必要每个比赛日都跑，还是开赛前预跑一次就够？**  
A: **必须每个比赛日都跑**，原因有四：
1. **市场锚定层每天在变**（权重 60%）。Polymarket / Kalshi 的赔率随资金流、伤病新闻、首发消息实时变动；锚点一变，`P_final = 0.60·P_market + 0.40·P_model` 跟着变，edge 和 Kelly stake 也变。
2. **DC 模型 `as_of` 截止日**。已完赛的小组赛结果会进入训练集刷新球队 α/β——例如阿根廷小组赛 3-0 大胜，会在 16 强预测时被吸收。一次性预跑等于用一个月前的过时强度算淘汰赛。
3. **首发 XI + 伤病只能赛前 1 小时内确认**。`API-Football /injuries` 按日期查询，主力缺阵通过 talent 层下调 λ；开赛前几周这个信号根本不存在。
4. **`bet --date` 只对指定日期出 slate**，没跑就没有当日推荐。

唯一一次性预跑还有用的场景是**看夺冠概率分布**（`market` / `simulation.json`），那个变化慢。但**下注建议必须每日刷新**。

**Q: 如何提前为明日比赛生成下注建议（避免半夜操作）？**  
A: 使用 `--date` 指定明日日期。`predict` 预测所有未完赛场次；`--date` 的作用是：
①以该日期为 DC 模型截止日（`as_of`），②将结果写入对应日期目录，③查询该日期的首发 / 伤病。
`bet --date` 则只从该目录里筛选出 `date == 指定日期` 的比赛生成建议。
```bash
PYTHONPATH=. python -m skill.helpers.cli predict --simulate --date 2026-06-23
PYTHONPATH=. python -m skill.helpers.cli bet --bankroll 10000 --date 2026-06-23
```
赛前 30 分钟再跑一次 `fetch --all` + `predict --date 2026-06-23` + `bet --date 2026-06-23`，
以获取最新首发和市场赔率。

---

## 11. 付费升级决策

项目所有核心功能（DC 模型、市场锚定、AH/OU 推荐、Kelly 下注）**全部在免费层
可用**。如果你想强化"市场锚定"层，有且仅有一个值得付费的升级，以及一个**明确不推荐**的常见付费源。

| 升级 | 决策 | 原因 |
|---|---|---|
| **Pinnacle 收盘价**（[The Odds API](https://the-odds-api.com) 基础付费档，~$30/月） | ✅ **推荐** | Pinnacle 收盘价是学界公认的"sharpest line"——低佣金、跟随聪明钱而非散户情绪。它是市场锚定层最值得花钱加的单一信号。配置只需在 `.env` 中设置 `ODDS_API_KEY`，加载器自动识别；无需改模型。 |
| **Pinnacle 历史 AH/OU 存档**（同一 key 升级到 Business 档，~$99/月） | ⚠ **二期** | 用于让球盘 / 大小盘的真实 ROI 历史回测。在赛事开始前不必要；待 P0.2b 启动后再升级。 |
| **Macau 澳彩盘 / 亚洲零售盘** | ❌ **不推荐** | 散户驱动的让球盘，反映的是中国公众资金而非聪明钱，与 Pinnacle 高度相关却更带噪——加了等于在共识里多塞一份相关信号，是噪音不是 alpha。无免费 API、无干净历史档，无法在本项目"必须 walk-forward 验证才能采纳"的纪律下接入。同样理由排除其他亚洲零售盘。 |

**核心原则**：花钱买**锐度（sharpness）和正交性（orthogonality）**——
Pinnacle 收盘价正是这种来源；不要花钱重复购买已经包含在共识里的散户信号。

---

## 附录：相关文档

- [`README.md`](../README.md) — 项目门面与高层介绍
- [`CHANGELOG.md`](../CHANGELOG.md) — 版本变化记录（Keep a Changelog 1.1.0）
- [`reports/backtests/FINDINGS.md`](../reports/backtests/FINDINGS.md) — 完整因子验证记录
- [`docs/competitor_analysis.md`](competitor_analysis.md) — 9 个 GitHub 同类项目横向对比
- [`.claude/plans/optimization_backlog.md`](../.claude/plans/optimization_backlog.md) — 当前优化路线图（开发者维度）
