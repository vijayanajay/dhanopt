# Collateral-Yield Playbook — the sandbox's one certified-positive action

Written 2026-10-01. Sources: RBI policy rates (repo 5.25% / SDF 5.00% — held
Aug 2026 MPC, unchanged since), overnight-fund category yields (~5.0–5.8%,
3-yr category avg 5.82%), SEBI F&O collateral rules (liquid/overnight funds
count as the **cash** component; ~10–15% broker haircut on fund units), debt-
fund taxation (slab rate for everything bought after 01-Apr-2023 — no LTCG
break). Rates move with the MPC; re-check quarterly.

**The finding it monetizes:** every strategy family in this sandbox is
falsified (see [RETROSPECTIVE.md](RETROSPECTIVE.md)) — but the account's idle
₹2L can earn the risk-free rate while sitting in the demat/broker account,
independent of all research. This is the only certified-positive action.

## 1. Instrument choice (one decision, made here)

| Instrument | Yield (Oct-2026) | Duration/credit risk | Liquidity | Verdict |
|---|---|---|---|---|
| **Overnight fund (growth plan)** | ~5.0–5.5% | none (overnight maturity) | redemption T+1, no exit load | **USE — default** |
| Liquid fund (growth) | ~5.2–5.7% | days (tiny) | T+1; exit load ~0.007%/day ≤ 7 days | fine alternative; exit-load floor irrelevant once pledged long-term |
| LiquidBees ETF | ~5% | none | intraday sell; monthly IDCW (taxed at slab) | more moving parts (units, dividend tax) — skip |
| Savings a/c cash | ~3% | none | instant | the baseline you're beating: 2–2.5 pts × ₹2L = ₹4–5k/yr left on the table |
| Equity / gilt / corporate-bond funds | higher *maybe* | real | real | **never pledge margin money into these** — a NAV drawdown on collateral is strategy risk, not yield |

Pick **one large overnight fund** (AUM > ₹10k cr, direct plan, growth option —
e.g. any of the big AMC's overnight funds; the category is commoditized, the
cheapest direct plan wins). Growth plan: tax deferred to redemption; IDCW
plans tax annually at slab for zero benefit — avoid.

## 2. Operation (one-time setup, ~15 minutes)

1. Transfer the idle ₹2L from the bank into the broker account.
2. Buy the chosen overnight fund's units (same platform; same-day NAV if
   before the cut-off).
3. **Pledge** the units via the broker's margin-pledge flow (units stay in
   your demat with a lien; margin value appears after pledge confirmation,
   typically same/next day). Pledge ~₹1.8L of the ₹2L and keep the rest in
   cash as a buffer — see haircut math below.
4. Done. Yield accrues daily in the fund's NAV; margin availability is
   unchanged; no orders, no monitoring.

Broker specifics vary (pledge confirmation flow, per-scrip pledge charge
₹0–30+GST — one-time per instrument, immaterial at ₹2L). The 50% cash rule
(SEBI) counts pledged liquid/overnight funds as the **cash component**, so
should the account ever trade F&O again, the same pledge supports margin —
no rework needed.

## 3. The math on ₹2L (honest, Oct-2026 rates)

- Haircut ~10% on pledged fund units → pledge ₹1.8L, keep ₹20k cash buffer.
  The ₹20k buffer also earns fund yield if parked in the fund *before*
  haircut economics matter — simplest: pledge ₹1.8L, buy ₹1.8L of units,
  leave ₹20k as sweep-in cash.
- Gross yield: ₹2,00,000 × ~5.3% ≈ **₹10,600/yr** (₹885/month avg).
- Tax: debt-fund gains at slab (post-2023 rules). Net:
  - 30% bracket → **~₹7,400/yr**
  - 20% bracket → **~₹8,500/yr**
  - 5% bracket → **~₹10,000/yr**
- vs leaving it in savings (3%): the play earns the 2.3-pt spread ≈ ₹4,600/yr
  extra pre-tax.

**Note on the docs' ₹10–13k/yr:** that range was written when the repo was
6.0–6.5%. At Oct-2026 rates the honest gross is ~₹10–11k; post-tax at the top
slab ~₹7–8k. The handoff and retrospective are resynced to this number.

## 4. Risks (all small, all named)

- **Fund NAV risk:** overnight funds hold 1-day maturity paper — NAV
  drawdowns are ~zero outside a systemic event (the 2019-ILFS-style tail;
  overnight funds were the least-hit category). Acceptable for margin money.
- **Broker/counterparty risk:** units stay in your demat under lien; the
  claim is on the fund, not the broker. Brokers can raise haircuts in stress
  (→ margin shortfall, not principal loss).
- **Liquidity:** redemption T+1 — do not pledge money needed tomorrow.
- **Tax drag:** slab rate, annual; growth plan defers realization.

## 5. Monitoring (quarterly, 5 minutes)

- Repo/SDF level vs the fund's 7-day yield (if the spread to SDF 5.00%
  widens beyond ~1 pt, shop the category — never chase credit for yield).
- Pledge health in the broker's margin statement (haircut drift).
- That's all. This play has no edge to monitor — it has a rate to collect.
