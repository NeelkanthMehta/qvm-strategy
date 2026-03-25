# QVM Composite Score + Macro Timing Strategy
# QuantConnect LEAN Algorithm
# Author: Neelkanth Mehta
#
# STRATEGY OVERVIEW:
# A systematic equity strategy combining a three-pillar Quality-Value-Momentum
# composite score with a dual-signal macro timing overlay.
#
# SCORING MODEL — QVM Composite Score (0-9):
#
#   QUALITY (3 signals) — based on Novy-Marx (2013) and AQR QMJ framework
#     Q1: Gross Profit / Total Assets > cross-sectional median (profitability premium)
#     Q2: Operating Cash Flow / Total Assets > 0 (cash earnings quality)
#     Q3: CFO > Net Income i.e. accruals < 0 (earnings quality / Sloan 1996)
#
#   VALUE (3 signals) — EBIT/EV based, more robust than B/M across regimes
#     V1: EBIT / Enterprise Value > cross-sectional median (Greenblatt 2005)
#     V2: Free Cash Flow / Price > cross-sectional median (O'Shaughnessy 2012)
#     V3: Debt/EBITDA declining YoY (balance sheet improvement)
#
#   MOMENTUM (3 signals) — fundamental + price momentum (Novy-Marx 2015)
#     M1: 12-month price return > 0 (trend confirmation)
#     M2: Revenue growth YoY > 0 (fundamental momentum)
#     M3: EPS growth YoY > 0 (earnings momentum)
#
# MACRO TIMING OVERLAY:
#   Gate 1: IWD > 200-day SMA (value index regime filter)
#   Gate 2: VIX < 30 (volatility regime filter)
#   Both must be active to invest; otherwise 100% cash
#
# PORTFOLIO ARCHITECTURE — TWO SLEEVE SYSTEM:
#   ACTIVE SLEEVE:    QVM-selected equities, equal-weighted
#                     Size: deployable capital only
#   PROTECTED SLEEVE: GLD (50%) + BIL (50%), always invested
#                     Ratchets up to 80% of all-time high value
#                     Never follows macro timing gate
#   PROFIT LOCK-IN:   At each rebalance, 80% of profits above
#                     high-water mark moved to protected sleeve
#   Stop loss:        None — annual rebalance is the exit
#
# REFERENCES:
#   Novy-Marx, R. (2013). The other side of value: The gross profitability premium.
#   Asness, C., Frazzini, A., & Pedersen, L. (2014). Quality Minus Junk.
#   Greenblatt, J. (2005). The Little Book That Beats the Market.
#   Novy-Marx, R. (2015). Fundamentally, momentum is fundamental momentum.
#   He, S. & Narayanamoorthy, G. (2017). Earnings acceleration and stock returns.
#   Sloan, R. (1996). Do stock prices fully reflect information in accruals?
#
# PERIOD: January 2015 - December 2025
# IN-SAMPLE:     2015-2022 (stop loss optimisation)
# OUT-OF-SAMPLE: 2023-2025 (performance attribution tear sheet)
# BENCHMARK: IWD (iShares Russell 1000 Value ETF)

from AlgorithmImports import *

class QVMCompositeStrategy(QCAlgorithm):

    def initialize(self):
        # ── BACKTEST PARAMETERS ──────────────────────────────────
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2025, 12, 31)
        self.set_cash(1_000_000)
        self.set_benchmark("IWD")

        # ── UNIVERSE ─────────────────────────────────────────────
        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.universe_filter)

        # ── PARAMETERS ───────────────────────────────────────────
        self.MAX_LONG          = 25
        self.QVM_MIN           = 6      # minimum QVM score to qualify
        self.PROTECTION_RATE   = 0.80   # % of profits locked into safe haven
        self.INITIAL_CAPITAL   = 1_000_000
        # No trailing stop — annual rebalance is the exit mechanism

        # ── MARKET TIMING — IWD 200-SMA + VIX ───────────────────
        self.iwd     = self.add_equity("IWD", Resolution.DAILY).symbol
        self.iwd_sma = self.sma("IWD", 200, Resolution.DAILY)

        # ── PROTECTED SLEEVE ASSETS ───────────────────────────────
        # Always invested regardless of macro timing gate
        # GLD: Gold ETF (inflation hedge, crisis protection)
        # BIL: SPDR Bloomberg 1-3 Month T-Bill ETF (cash equivalent)
        self.gld = self.add_equity("GLD", Resolution.DAILY).symbol
        self.bil = self.add_equity("BIL", Resolution.DAILY).symbol

        try:
            self.vix = self.add_data(CBOE, "VIX", Resolution.DAILY).symbol
            self.vix_available = True
        except:
            self.vix_available = False
            self.log("VIX unavailable - using IWD SMA only")

        self.VIX_THRESHOLD = 30.0

        # ── FUNDAMENTAL + PRICE CACHE ────────────────────────────
        # Stores prior year data for YoY comparisons
        # (one_year accessor returns None in LEAN — cache is the fix)
        # Also stores price for 12-month momentum signal
        self.prev_cache   = {}
        self.rebalance_count = 0

        # ── REBALANCE SCHEDULING ─────────────────────────────────
        # Scheduled monthly, gated to April only inside rebalance()
        # April 1 ensures Dec fiscal year filings are available
        self.schedule.on(
            self.date_rules.month_start("IWD"),
            self.time_rules.after_market_open("IWD", 30),
            self.rebalance
        )

        # ── TRACKING ─────────────────────────────────────────────
        self.long_symbols        = []
        self.stop_losses         = {}   # unused — no trailing stop
        self.below_sma_days      = 0    # consecutive days IWD below SMA
        self.DEFENSIVE_THRESHOLD = 5    # days below SMA before active exit
        self.high_water_mark     = self.INITIAL_CAPITAL  # ratchets up, never down
        self.protected_value     = 0    # current value locked in safe haven

        # ── WARM-UP ──────────────────────────────────────────────
        self.set_warm_up(timedelta(210))

        self.log(f"QVM+Protection | QVM>={self.QVM_MIN} | Protection: {self.PROTECTION_RATE*100:.0f}% | GLD+BIL sleeve")


    # ════════════════════════════════════════════════════════════
    # UNIVERSE — broad US equities, no value filter
    # QVM score handles stock selection internally
    # ════════════════════════════════════════════════════════════

    def universe_filter(self, fundamentals):
        filtered = [
            f for f in fundamentals
            if f.price > 5
            and f.market_cap > 300e6
            and f.has_fundamental_data
            and f.financial_statements.income_statement.total_revenue.twelve_months > 0
        ]
        # Sort by dollar volume for liquidity — top 600
        filtered.sort(key=lambda x: x.dollar_volume, reverse=True)
        return [f.symbol for f in filtered[:600]]


    # ════════════════════════════════════════════════════════════
    # EXTRACT TO CACHE
    # ════════════════════════════════════════════════════════════

    def extract_to_cache(self, f):
        """
        Extract all data needed for QVM scoring into a plain dict.
        Stores both fundamentals and current price for momentum.
        """
        try:
            fs  = f.financial_statements
            ops = fs.income_statement
            bal = fs.balance_sheet
            cfl = fs.cash_flow_statement

            ta  = bal.total_assets.twelve_months
            if not ta or ta <= 0:
                return None

            # Revenue and earnings
            rev    = ops.total_revenue.twelve_months or 0
            ni     = ops.net_income.twelve_months or 0
            cfo    = cfl.operating_cash_flow.twelve_months or 0

            # Gross profit
            cogs   = 0
            try:
                cogs = ops.cost_of_revenue.twelve_months or 0
            except Exception:
                pass
            gross_profit = rev - cogs

            # EBIT (Operating Income)
            ebit = 0
            try:
                ebit = ops.operating_income.twelve_months or 0
            except Exception:
                # Approximate: Net Income + Interest + Taxes
                try:
                    interest = ops.interest_expense.twelve_months or 0
                    tax      = ops.tax_provision.twelve_months or 0
                    ebit     = ni + abs(interest) + abs(tax)
                except Exception:
                    ebit = ni

            # Capital expenditures (for FCF)
            capex = 0
            try:
                capex = abs(cfl.capital_expenditure.twelve_months or 0)
            except Exception:
                pass
            fcf = cfo - capex

            # Enterprise Value components
            mkt_cap = f.market_cap or 0
            lt_debt = bal.long_term_debt.twelve_months or 0
            st_debt = 0
            try:
                st_debt = bal.current_debt.twelve_months or 0
            except Exception:
                pass
            cash    = bal.cash_and_cash_equivalents.twelve_months or 0
            ev      = max(mkt_cap + lt_debt + st_debt - cash, 1)

            # EBITDA (for debt/EBITDA)
            ebitda = 0
            try:
                da     = cfl.depreciation_and_amortization.twelve_months or 0
                ebitda = ebit + da
            except Exception:
                ebitda = ebit

            total_debt = lt_debt + st_debt
            debt_ebitda = total_debt / ebitda if ebitda > 0 else 999

            # EPS
            eps = 0
            try:
                sh  = bal.share_issued.twelve_months or 1
                eps = ni / sh if sh > 0 else 0
            except Exception:
                eps = 0

            # Current price (for M1 momentum signal)
            price = f.price or 0

            return {
                "ta":           ta,
                "rev":          rev,
                "ni":           ni,
                "cfo":          cfo,
                "gross_profit": gross_profit,
                "ebit":         ebit,
                "fcf":          fcf,
                "ev":           ev,
                "mkt_cap":      mkt_cap,
                "price":        price,
                "ebitda":       ebitda,
                "debt_ebitda":  debt_ebitda,
                "eps":          eps,
                "lt_debt":      lt_debt,
            }
        except Exception:
            return None


    # ════════════════════════════════════════════════════════════
    # QVM SCORE COMPUTATION
    # ════════════════════════════════════════════════════════════

    def compute_qvm(self, curr, prev, gp_median, ev_median, fcf_median):
        """
        Compute QVM Composite Score (0-9).

        curr, prev: dicts from extract_to_cache()
        gp_median:  cross-sectional median of gross_profit/ta (for Q1)
        ev_median:  cross-sectional median of ebit/ev (for V1)
        fcf_median: cross-sectional median of fcf/mkt_cap (for V2)
        """
        try:
            ta   = curr["ta"]
            if ta <= 0:
                return None

            # ── QUALITY SIGNALS ──────────────────────────────────

            # Q1: Gross Profit / Total Assets > cross-sectional median
            gp_ratio = curr["gross_profit"] / ta if ta > 0 else 0
            Q1 = 1 if gp_ratio > gp_median else 0

            # Q2: Operating Cash Flow / Total Assets > 0
            Q2 = 1 if curr["cfo"] > 0 else 0

            # Q3: CFO > Net Income (accruals < 0 = high earnings quality)
            Q3 = 1 if curr["cfo"] > curr["ni"] else 0

            # ── VALUE SIGNALS ─────────────────────────────────────

            # V1: EBIT / Enterprise Value > cross-sectional median
            ebit_ev = curr["ebit"] / curr["ev"] if curr["ev"] > 0 else 0
            V1 = 1 if ebit_ev > ev_median else 0

            # V2: Free Cash Flow / Market Cap > cross-sectional median
            fcf_yield = curr["fcf"] / curr["mkt_cap"] if curr["mkt_cap"] > 0 else 0
            V2 = 1 if fcf_yield > fcf_median else 0

            # V3: Debt/EBITDA declining YoY (balance sheet improving)
            V3 = 1 if curr["debt_ebitda"] < prev["debt_ebitda"] else 0

            # ── MOMENTUM SIGNALS ─────────────────────────────────

            # M1: 12-month price return > 0 (price trend confirmation)
            # Compare current price (from live securities) vs prior year cache
            M1 = 1 if (prev["price"] > 0 and
                       curr["price"] > prev["price"]) else 0

            # M2: Revenue growth YoY > 0 (fundamental momentum)
            M2 = 1 if (prev["rev"] > 0 and
                       curr["rev"] > prev["rev"]) else 0

            # M3: EPS growth YoY > 0 (earnings momentum)
            M3 = 1 if (prev["eps"] != 0 and
                       curr["eps"] > prev["eps"]) else 0

            score = Q1 + Q2 + Q3 + V1 + V2 + V3 + M1 + M2 + M3

            return score

        except Exception:
            return None


    # ════════════════════════════════════════════════════════════
    # MARKET TIMING
    # ════════════════════════════════════════════════════════════

    def market_is_investable(self):
        if self.is_warming_up or not self.iwd_sma.is_ready:
            return False

        above_sma = (self.securities[self.iwd].price >
                     self.iwd_sma.current.value)

        if self.vix_available:
            try:
                vix_val = self.securities[self.vix].price
                vix_ok  = 0 < vix_val < self.VIX_THRESHOLD
            except:
                vix_ok = True
        else:
            vix_ok = True

        return above_sma and vix_ok


    # ════════════════════════════════════════════════════════════
    # REBALANCE — Annual in April
    # ════════════════════════════════════════════════════════════

    def rebalance(self):
        if self.is_warming_up:
            return

        # Annual gate — only execute in April
        if self.time.month != 4:
            return

        self.rebalance_count += 1
        investable = self.market_is_investable()
        self.log(f"Rebalance: {self.time.date()} | "
                 f"Investable: {investable} | Run: {self.rebalance_count}")

        # ── Step 1: Build current year cache ─────────────────────
        new_cache = {}
        universe  = [s for s in self.active_securities.keys()
                     if s != self.iwd]

        for symbol in universe:
            try:
                f = self.active_securities[symbol].fundamentals
                if f is None:
                    continue
                cached = self.extract_to_cache(f)
                if cached is not None:
                    # Update price from live feed (more accurate than fundamental)
                    cached["price"] = self.securities[symbol].price
                    new_cache[symbol] = cached
            except Exception:
                continue

        self.log(f"Cached: {len(new_cache)} | Prev: {len(self.prev_cache)}")

        # ── Step 2: First rebalance — cache only ─────────────────
        if self.rebalance_count == 1:
            self.prev_cache = new_cache
            self.log("First rebalance — caching for YoY baseline")
            return

        # ── Step 3: Market timing check ──────────────────────────
        if not investable:
            self.log("Timing gate CLOSED — active sleeve to cash, protected stays")
            protected_symbols = {self.gld, self.bil, self.iwd}
            for symbol in list(self.portfolio.keys()):
                if symbol not in protected_symbols and self.portfolio[symbol].invested:
                    self.liquidate(symbol)
            self.long_symbols   = []
            self.stop_losses    = {}
            self.below_sma_days = 0
            self.prev_cache     = new_cache
            return

        # ── Step 4: Compute cross-sectional medians ───────────────
        # Used for Q1 (gross profit yield), V1 (EBIT/EV), V2 (FCF yield)
        gp_ratios  = []
        ev_ratios  = []
        fcf_yields = []

        for symbol in new_cache:
            d = new_cache[symbol]
            ta = d["ta"]
            if ta > 0:
                gp_ratios.append(d["gross_profit"] / ta)
            if d["ev"] > 0:
                ev_ratios.append(d["ebit"] / d["ev"])
            if d["mkt_cap"] > 0:
                fcf_yields.append(d["fcf"] / d["mkt_cap"])

        gp_ratios.sort();  ev_ratios.sort();  fcf_yields.sort()

        gp_med  = gp_ratios[len(gp_ratios)//2]   if gp_ratios  else 0
        ev_med  = ev_ratios[len(ev_ratios)//2]    if ev_ratios  else 0
        fcf_med = fcf_yields[len(fcf_yields)//2]  if fcf_yields else 0

        # ── Step 5: Score all stocks ──────────────────────────────
        scores = {}
        for symbol in new_cache:
            if symbol not in self.prev_cache:
                continue
            score = self.compute_qvm(
                new_cache[symbol],
                self.prev_cache[symbol],
                gp_med, ev_med, fcf_med
            )
            if score is not None:
                scores[symbol] = score

        high = sum(1 for s in scores.values() if s >= self.QVM_MIN)
        self.log(f"Scored: {len(scores)} | QVM>={self.QVM_MIN}: {high}")

        # ── Step 6: Select portfolio ──────────────────────────────
        sorted_scores   = sorted(scores.items(),
                                 key=lambda x: x[1], reverse=True)
        long_candidates = [s for s, sc in sorted_scores
                           if sc >= self.QVM_MIN][:self.MAX_LONG]

        if not long_candidates:
            self.log(f"No stocks with QVM>={self.QVM_MIN} — active sleeve to cash")
            protected_symbols = {self.gld, self.bil, self.iwd}
            for symbol in list(self.portfolio.keys()):
                if symbol not in protected_symbols and self.portfolio[symbol].invested:
                    self.liquidate(symbol)
            self.long_symbols = []
            self.stop_losses  = {}
            self.prev_cache   = new_cache
            return

        # ── Step 7: Two-sleeve portfolio construction ─────────────

        total_value = self.portfolio.total_portfolio_value

        # Update high water mark
        if total_value > self.high_water_mark:
            # Lock 80% of new profits into protected sleeve
            new_profit          = total_value - self.high_water_mark
            profit_to_protect   = new_profit * self.PROTECTION_RATE
            self.protected_value = self.protected_value + profit_to_protect
            self.high_water_mark = total_value
            self.log(f"HWM updated: ${total_value:,.0f} | "
                     f"Protected: ${self.protected_value:,.0f} | "
                     f"New lock-in: ${profit_to_protect:,.0f}")

        # Protected sleeve fraction of total portfolio
        protected_weight = min(self.protected_value / total_value, 0.95)                            if total_value > 0 else 0
        active_weight    = 1.0 - protected_weight

        self.log(f"Sleeves | Active: {active_weight*100:.1f}% | "
                 f"Protected: {protected_weight*100:.1f}%")

        # Liquidate active positions no longer in candidates
        protected_symbols = {self.gld, self.bil, self.iwd}
        for symbol in list(self.portfolio.keys()):
            if symbol in protected_symbols:
                continue
            if (self.portfolio[symbol].invested and
                    symbol not in long_candidates):
                self.liquidate(symbol)

        # Build active sleeve — QVM stocks
        if long_candidates and active_weight > 0.01:
            stock_weight = (active_weight * 0.95) / len(long_candidates)
            for symbol in long_candidates:
                self.set_holdings(symbol, stock_weight)

        # Build protected sleeve — GLD 50% + BIL 50%
        if protected_weight > 0.001:
            self.set_holdings(self.gld, protected_weight * 0.50)
            self.set_holdings(self.bil, protected_weight * 0.50)
        else:
            # No profits locked yet — GLD/BIL at zero
            self.set_holdings(self.gld, 0)
            self.set_holdings(self.bil, 0)

        self.long_symbols = long_candidates
        self.log(f"Active: {len(long_candidates)} stocks @ "
                 f"{stock_weight*100:.1f}% each | "
                 f"Protected: GLD+BIL @ {protected_weight*100:.1f}%")

        # ── Step 8: Roll cache ────────────────────────────────────
        self.prev_cache = new_cache


    # ════════════════════════════════════════════════════════════
    # ON DATA — Daily trailing stop + defensive exit
    # ════════════════════════════════════════════════════════════

    def on_data(self, data):
        if self.is_warming_up:
            return

        # Defensive exit: only after 5 consecutive days below IWD SMA
        # Avoids whipsaw exits on brief dips
        currently_investable = self.market_is_investable()

        if not currently_investable:
            self.below_sma_days += 1
        else:
            self.below_sma_days = 0

        if self.below_sma_days >= self.DEFENSIVE_THRESHOLD:
            if any(self.portfolio[s].invested
                   for s in self.long_symbols
                   if s in self.portfolio):
                self.log(f"Defensive exit ({self.below_sma_days}d below SMA): "
                         f"{self.time.date()}")
                # Liquidate active sleeve only — protected sleeve stays invested
                protected_symbols = {self.gld, self.bil, self.iwd}
                for symbol in list(self.long_symbols):
                    if symbol not in protected_symbols:
                        self.liquidate(symbol)
                self.long_symbols   = []
                self.stop_losses    = {}
                self.below_sma_days = 0


    # ════════════════════════════════════════════════════════════
    # ON SECURITIES CHANGED
    # ════════════════════════════════════════════════════════════

    def on_securities_changed(self, changes):
        for security in changes.removed_securities:
            symbol = security.symbol
            self.stop_losses.pop(symbol, None)
            if symbol in self.long_symbols:
                self.long_symbols.remove(symbol)
