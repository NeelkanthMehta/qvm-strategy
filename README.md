# QVM Composite Score + Macro Timing Strategy

A systematic US equity strategy combining a **9-signal Quality-Value-Momentum composite score** with a dual macro timing overlay and a two-sleeve profit protection architecture. Built and backtested on QuantConnect LEAN (Python), covering January 2015 – December 2025.

---

## Strategy Overview

Most systematic strategies face a fundamental tension: fundamental signals are annual, but markets move daily. This strategy resolves that tension with three layered mechanisms:

1. **QVM Scoring** — selects stocks with simultaneously high quality, attractive valuation, and positive momentum at each annual rebalance
2. **Macro Timing Gate** — exits the active equity sleeve when the value index enters a sustained downtrend, avoiding the worst of bear market drawdowns
3. **Profit Protection Ratchet** — permanently transfers 80% of new profits into a GLD + BIL safe haven sleeve at each rebalance, structurally preserving gains

---

## Scoring Model — QVM Composite Score (0–9)

Each signal contributes one binary point. Stocks with QVM ≥ 6 qualify for the active portfolio.

### Quality Pillar (Q1–Q3)
*Separates genuine earnings quality from accounting artifacts*

| Signal | Condition | Source |
|--------|-----------|--------|
| Q1 | Gross Profit / Total Assets > cross-sectional median | Novy-Marx (2013) |
| Q2 | Operating Cash Flow / Total Assets > 0 | Asness, Frazzini & Pedersen — QMJ (2014) |
| Q3 | Operating CFO > Net Income (accruals < 0) | Sloan (1996) |

### Value Pillar (V1–V3)
*EBIT/EV-based valuation — more robust than Book/Market across regimes*

| Signal | Condition | Source |
|--------|-----------|--------|
| V1 | EBIT / Enterprise Value > cross-sectional median | Greenblatt (2005) |
| V2 | Free Cash Flow / Market Cap > cross-sectional median | O'Shaughnessy (2012) |
| V3 | Debt/EBITDA declining year-over-year | — |

### Momentum Pillar (M1–M3)
*Confirms market recognition of quality and value*

| Signal | Condition | Source |
|--------|-----------|--------|
| M1 | 12-month price return > 0 | Jegadeesh & Titman (1993) |
| M2 | Revenue growth year-over-year > 0 | Novy-Marx (2015) |
| M3 | EPS growth year-over-year > 0 | He & Narayanamoorthy (2017) |

---

## Macro Timing Overlay

Two independent signals must both be active for the equity sleeve to be invested:

- **IWD 200-day SMA** — active sleeve invested only when IWD (iShares Russell 1000 Value ETF) trades above its 200-day moving average. IWD is used instead of SPY for style consistency — the strategy is evaluated against the same index it monitors.
- **VIX < 30** — active sleeve exits during elevated volatility regimes.

A **5-day confirmation filter** prevents whipsaw exits on single-day dips. The protected sleeve (GLD + BIL) is never affected by the timing gate.

---

## Profit Protection Architecture

At each annual rebalance, if portfolio value exceeds the prior high-water mark:

```
new_profit        = portfolio_value - high_water_mark
profit_to_protect = new_profit × 0.80
protected_sleeve += profit_to_protect
high_water_mark   = portfolio_value   ← ratchets up, never down
```

Protected capital is allocated **50% GLD (gold ETF) + 50% BIL (T-bill ETF)** — a crisis-resilient, inflation-hedged safe haven that stays invested regardless of market conditions.

**Observed ratchet progression (2015–2025):**

| Year | High-Water Mark | Protected Sleeve | Active Allocation |
|------|----------------|-----------------|-------------------|
| 2016 | $1,000,000 | $0 | 100% |
| 2017 | $1,158,137 | $126,509 | 89.1% |
| 2018 | $1,334,412 | $267,529 | 80.0% |
| 2022 | $1,434,542 | $347,634 | 75.8% |
| 2025 | $1,512,812 | $410,250 | 72.9% |

---

## Results (2015–2025)

| Metric | QVM + Protection | IWD Benchmark |
|--------|-----------------|---------------|
| Total Return | 49.7% | 98.7% |
| CAGR | ~4.0% | ~7.1% |
| Best 12M Sharpe | **3.09** (Nov 2017) | — |
| Market Beta | **0.10** | 1.00 |
| Max Drawdown | ~11% | ~20% |
| Profits locked in GLD+BIL | **$410,250 (27%)** | — |

The strategy underperforms passive IWD on a full-period CAGR basis — consistent with post-publication factor decay documented in the academic literature. The primary contribution is the architecture: low-beta, crisis-resilient equity exposure with structural profit preservation.

---

## Repository Structure

```
qvm-strategy/
├── main.py          # QuantConnect LEAN trading algorithm
├── research.ipynb   # Signal validation, universe analysis, profit protection
└── README.md
```

---

## Portfolio

Part of a broader quantitative research portfolio — [neelkanthmehta.vercel.app](https://neelkanthmehta.vercel.app)

---

## References

- Novy-Marx, R. (2013). The other side of value: The gross profitability premium. *Journal of Financial Economics*.
- Asness, C., Frazzini, A., & Pedersen, L. (2014). Quality minus junk. *Review of Accounting Studies*.
- Sloan, R. (1996). Do stock prices fully reflect information in accruals and cash flows about future earnings? *The Accounting Review*.
- Greenblatt, J. (2005). *The Little Book That Beats the Market*. Wiley.
- O'Shaughnessy, J. (2012). *What Works on Wall Street*. McGraw-Hill.
- Jegadeesh, N. & Titman, S. (1993). Returns to buying winners and selling losers. *Journal of Finance*.
- Novy-Marx, R. (2015). Fundamentally, momentum is fundamental momentum. *NBER Working Paper*.
- He, S. & Narayanamoorthy, G. (2017). Earnings acceleration and stock returns. *Journal of Accounting and Economics*.
