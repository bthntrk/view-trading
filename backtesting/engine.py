"""
backtesting/engine.py
======================
Geriye dönük test (backtest) motoru.

Son 1 yıllık OHLCV verisi üzerinde stratejiyi simüle eder.
Walk-forward yaklaşımıyla her mum üzerinde sırayla değerlendirme yapar.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from config import config, BacktestConfig
from indicators.volume_profile import VolumeProfileCalculator, VolumeProfileLevels
from indicators.trend_filter import TrendFilter, Trend
from risk_management.manager import RiskManager, RiskParameters
from strategy.signal import StrategyEngine, Signal

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    """Backtest içinde gerçekleşen tek bir işlem."""
    symbol: str
    side: str
    entry_idx: int
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    position_size: float
    pnl: float
    status: str    # WIN / LOSS / STOPPED


@dataclass
class BacktestResult:
    """Backtest sonuçları özeti."""
    symbol: str
    total_trades: int
    winners: int
    losers: int
    win_rate: float
    gross_profit: float
    gross_loss: float
    net_pnl: float
    max_drawdown: float
    final_balance: float
    trades: List[BacktestTrade] = field(default_factory=list)

    def print_summary(self) -> None:
        """Konsola özet yazdırır."""
        sep = "=" * 55
        print(f"\n{sep}")
        print(f"  BACKTEST SONUÇLARI — {self.symbol}")
        print(sep)
        print(f"  Toplam İşlem   : {self.total_trades}")
        print(f"  Kazanan        : {self.winners}")
        print(f"  Kaybeden       : {self.losers}")
        print(f"  Win Rate       : {self.win_rate:.1%}")
        print(f"  Brüt Kar       : {self.gross_profit:+.2f} $")
        print(f"  Brüt Zarar     : {self.gross_loss:+.2f} $")
        print(f"  Net Kar        : {self.net_pnl:+.2f} $")
        print(f"  Max Drawdown   : {self.max_drawdown:.2%}")
        print(f"  Final Bakiye   : {self.final_balance:.2f} $")
        print(sep)


class BacktestEngine:
    """
    Stratejiyi geçmiş veri üzerinde çalıştıran backtest motoru.

    Çalışma mantığı:
    ----------------
    1. Veriyi warm-up periyodu kadar kaydırarak başlar (EMA-200 için).
    2. Her mum için, o ana kadar bilinen veriye dayanarak sinyal üretir.
    3. Sinyal üretilirse risk parametrelerini hesaplar ve simüle eder.
    4. Sonraki mumlar SL/TP kontrolü için kullanılır.
    """

    def __init__(self, cfg: Optional[BacktestConfig] = None) -> None:
        self._cfg = cfg or config.backtest
        self._strategy = StrategyEngine()
        self._risk_mgr = RiskManager()
        self._commission = self._cfg.commission_pct

    # ------------------------------------------------------------------
    # Ana arayüz
    # ------------------------------------------------------------------

    def run(self, symbol: str, df: pd.DataFrame) -> BacktestResult:
        """
        Tek sembol üzerinde backtest çalıştırır.

        Parameters
        ----------
        symbol : İşlem çifti
        df     : Tam OHLCV verisi (en az 365 günlük önerilir)

        Returns
        -------
        BacktestResult
        """
        logger.info("Backtest başlıyor: %s | %d mum", symbol, len(df))

        # Warm-up: EMA-200 için minimum 200 mum gerekli
        warmup = config.trend.ema_slow + 20
        if len(df) < warmup + 10:
            logger.error("Yetersiz veri: %d mum < %d (warmup)", len(df), warmup)
            return self._empty_result(symbol)

        balance = self._cfg.initial_balance
        equity_curve: List[float] = [balance]
        trades: List[BacktestTrade] = []
        open_trade: Optional[Tuple[int, RiskParameters, str]] = None  # (bar_idx, params, symbol)

        for i in range(warmup, len(df)):
            window = df.iloc[: i + 1]
            current_candle = df.iloc[i]
            high = float(current_candle["high"])
            low = float(current_candle["low"])
            close = float(current_candle["close"])

            # Açık pozisyon varsa SL / TP kontrolü
            if open_trade is not None:
                entry_bar, rp, _ = open_trade
                trade, balance = self._check_exit(
                    rp, high, low, close, balance, i, entry_bar
                )
                if trade:
                    trades.append(trade)
                    open_trade = None
                equity_curve.append(balance)
                continue

            # Sinyal üretimi (son muma kadar olan pencere)
            signal: Optional[Signal] = self._strategy.evaluate(symbol, window)

            if signal:
                rp = self._risk_mgr.calculate(
                    side=signal.side,
                    entry_price=signal.price,
                    balance=balance,
                )
                if rp:
                    commission = signal.price * rp.position_size * self._commission
                    balance -= commission
                    open_trade = (i, rp, signal.side)
                    logger.debug(
                        "Backtest trade açıldı: bar=%d %s @ %.4f",
                        i, signal.side, signal.price
                    )

            equity_curve.append(balance)

        # Kapanmadan kalan pozisyonu son fiyatla kapat
        if open_trade is not None:
            entry_bar, rp, side = open_trade
            last_close = float(df.iloc[-1]["close"])
            trade, balance = self._check_exit(
                rp, last_close, last_close, last_close,
                balance, len(df) - 1, entry_bar, force_close=True
            )
            if trade:
                trades.append(trade)

        return self._compile_result(symbol, trades, balance, equity_curve)

    # ------------------------------------------------------------------
    # Yardımcı metodlar
    # ------------------------------------------------------------------

    def _check_exit(
        self,
        rp: RiskParameters,
        high: float,
        low: float,
        close: float,
        balance: float,
        bar_idx: int,
        entry_bar: int,
        force_close: bool = False,
    ) -> Tuple[Optional[BacktestTrade], float]:
        """Mum içinde SL / TP kontrolü yapar."""
        side = rp.side
        sl = rp.stop_loss
        tp = rp.take_profit

        exit_price = None
        status = None

        if side == "LONG":
            if low <= sl:
                exit_price = sl
                status = "STOPPED"
            elif high >= tp:
                exit_price = tp
                status = "WIN"
        else:  # SHORT
            if high >= sl:
                exit_price = sl
                status = "STOPPED"
            elif low <= tp:
                exit_price = tp
                status = "WIN"

        if force_close and exit_price is None:
            exit_price = close
            status = "WIN" if (
                (side == "LONG" and close > rp.entry_price) or
                (side == "SHORT" and close < rp.entry_price)
            ) else "LOSS"

        if exit_price is None:
            return None, balance

        # PnL
        commission = exit_price * rp.position_size * self._commission
        if side == "LONG":
            gross = (exit_price - rp.entry_price) * rp.position_size
        else:
            gross = (rp.entry_price - exit_price) * rp.position_size
        net_pnl = gross - commission
        balance += rp.risk_amount + net_pnl

        trade = BacktestTrade(
            symbol=rp.side,          # side bilgisi
            side=side,
            entry_idx=entry_bar,
            entry_price=rp.entry_price,
            exit_price=exit_price,
            stop_loss=sl,
            take_profit=tp,
            position_size=rp.position_size,
            pnl=net_pnl,
            status=status,
        )
        return trade, balance

    def _compile_result(
        self,
        symbol: str,
        trades: List[BacktestTrade],
        final_balance: float,
        equity_curve: List[float],
    ) -> BacktestResult:
        """Ham işlem listesinden BacktestResult oluşturur."""
        winners = [t for t in trades if t.pnl > 0]
        losers = [t for t in trades if t.pnl <= 0]
        gross_profit = sum(t.pnl for t in winners)
        gross_loss = sum(t.pnl for t in losers)
        net_pnl = gross_profit + gross_loss
        win_rate = len(winners) / len(trades) if trades else 0.0
        max_dd = self._max_drawdown(equity_curve)

        result = BacktestResult(
            symbol=symbol,
            total_trades=len(trades),
            winners=len(winners),
            losers=len(losers),
            win_rate=win_rate,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            net_pnl=net_pnl,
            max_drawdown=max_dd,
            final_balance=final_balance,
            trades=trades,
        )
        logger.info(
            "Backtest tamamlandı: %s | %d işlem | WinRate=%.1f%% | Net=%.2f$",
            symbol, len(trades), win_rate * 100, net_pnl
        )
        return result

    @staticmethod
    def _max_drawdown(equity: List[float]) -> float:
        """Maksimum drawdown'ı hesaplar (0.0 – 1.0 arası oran)."""
        if not equity:
            return 0.0
        arr = np.array(equity, dtype=np.float64)
        running_max = np.maximum.accumulate(arr)
        drawdowns = (running_max - arr) / running_max
        return float(np.max(drawdowns))

    def _empty_result(self, symbol: str) -> BacktestResult:
        return BacktestResult(
            symbol=symbol,
            total_trades=0,
            winners=0,
            losers=0,
            win_rate=0.0,
            gross_profit=0.0,
            gross_loss=0.0,
            net_pnl=0.0,
            max_drawdown=0.0,
            final_balance=self._cfg.initial_balance,
        )
