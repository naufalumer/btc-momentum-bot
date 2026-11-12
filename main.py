"""BTC momentum bot for make.fun "Race a BTC trading bot live for 24 hours".

Strategy (chosen by backtest on the published dev window; see TEST-REPORT.md):
  - One asset (CBBTC), long only, at most one open position, full size (100% of
    cash, capped by hello caps max_weight_bps).
  - Keep the last 60 one-minute closes. Enter when the 60-bar return exceeds
    +0.50%; while long, stay long while the 60-bar return stays at or above
    0%; exit (sell everything) as soon as it is below 0% (at least -1 bp:
    the return is integer basis points, so exiting on `<= 0` would also fire
    on a 0 bp print and whipsaw the bot out of a live rally — see
    TEST-REPORT.md, bug #1).
  - That is the whole rule. On the dev window it trades 4 times, stays flat
    through the 20-hour bleed, and finishes +$2.43 net of all fees.
  - Deterministic: no clock, no randomness, no environment, no files. The
    decision is a pure function of the closes seen so far. The bot never
    trades on a warm-up batch (orders there are rejected anyway).
  - max_slippage_bps 500: a normal 1-minute move is a few bps, so a fill at
    the next open is far inside it; the cap only guards against a wild gap.

Wire protocol: agent-fun/bars-replay/v1, via the kit's Python shim, copied
byte-identical into vendor/makefun_bars.py (a kit SDK shim kept under vendor/
is left out of the authorship counts per RULES.txt).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import makefun_bars

LOOKBACK = 60
ENTER_BPS = 50      # enter when 60-bar return > +0.50%
EXIT_BPS = 0        # exit when 60-bar return <= 0%
MAX_SLIPPAGE_BPS = 500

SYMBOL = "CBBTC"
_closes = []  # latest close per batch, as ints (price units)


def _ret_bps(now, then):
    # (now / then - 1) in basis points, integer-exact.
    return (now - then) * 10000 // then


def on_batch(state, batch):
    close = state.close(SYMBOL)
    if close is None:
        return []
    _closes.append(close)
    if state.warming_up:
        return []
    if len(_closes) <= LOOKBACK:
        return []
    ret = _ret_bps(close, _closes[-1 - LOOKBACK])
    held = state.positions.get(SYMBOL)
    if held is not None and held.qty > 0:
        # Exit only on a genuinely negative 60-bar return. ret is integer
        # basis points, so `ret <= 0` would also fire on a 0 bp print (a
        # +0.004 bp float move truncates to 0) and whipsaw the bot out of a
        # live rally; `ret < 0` needs at least -1 bp.
        if ret < EXIT_BPS:
            return [{"side": "sell", "symbol": SYMBOL, "qty": held.qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []
    if ret > ENTER_BPS:
        room = state.weight_room(SYMBOL)
        spend = state.cash if state.cash < room else room
        if spend < int(state.hello["fees"]["min_notional_quote_units"]):
            return []
        return [{"side": "buy", "symbol": SYMBOL,
                 "notional_quote_units": spend,
                 "max_slippage_bps": MAX_SLIPPAGE_BPS}]
    return []


makefun_bars.run(on_batch)
