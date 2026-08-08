"""
strategy/signal.py
==================
Sinyal veri modeli ve strateji motoru.

Volume Profile + EMA trend filtresi kombinasyonuyla
LONG ve SHORT sinyalleri üretir.
"""

import logging
from dataclasses import dataclass
from typing import Literal, Optional

import pandas as pd

from config import config, StrategyConfig
from indicators.volume_profile import VolumeProfileCalculator, VolumeProfileLevels
from indicators.trend_filter import TrendFilter, TrendResult

logger = logging.getLogger(__name__)

SignalSide = Literal["LONG", "SHORT"]

@dataclass(frozen=True)
class Signal:
    side: SignalSide
    symbol: str
    price: float
    poc: float
    vah: float
    val: float
    ema_fast: float
    ema_slow: float
    volume_ratio: float

    def __str__(self) -> str:
        return (
            f"[{self.side}] {self.symbol} @ {self.price:.4f} | "
            f"POC={self.poc:.4f} VolumeRatio={self.volume_ratio:.2f}x"
        )

class StrategyEngine:
    """
    Volume Profile + EMA trend filtresi strateji motoru.
    """
    def __init__(self, cfg: Optional[StrategyConfig] = None) -> None:
        self._cfg = cfg or config.strategy
        self._vp_calc = VolumeProfileCalculator()
        self._trend_filter = TrendFilter()
        # Soğuma kontrolü için hafıza sözlüğü
        self._last_signal_time = {}

    def evaluate(self, symbol: str, df: pd.DataFrame) -> Optional[Signal]:
        current_time = df.index[-1]

        # 1. Soğuma (Cooldown) Kontrolü
        if symbol in self._last_signal_time:
            time_since_last = current_time - self._last_signal_time[symbol]
            if time_since_last < pd.Timedelta(minutes=15):
                return None

        # Göstergeleri hesapla
        vp_levels: VolumeProfileLevels = self._vp_calc.calculate(df)
        trend_result: TrendResult = self._trend_filter.calculate(df)

        min_bars = config.trend.ema_slow + config.strategy.volume_ma_period + 5
        if len(df) < min_bars:
            return None

        # Son iki mum ve güncel değerler
        prev_candle = df.iloc[-2]
        last_candle = df.iloc[-1]
        current_price = float(last_candle["close"])

        # Hacim oranı hesaplama
        vol_ma = float(df["volume"].iloc[-self._cfg.volume_ma_period - 1:-1].mean())
        current_vol = float(last_candle["volume"])
        volume_ratio = current_vol / vol_ma if vol_ma > 0 else 0.0

        logger.info(
            f"DEBUG | {symbol} | Fiyat: {current_price:.2f} | "
            f"EMA50: {trend_result.ema_fast:.2f} | EMA200: {trend_result.ema_slow:.2f} | "
            f"POC {vp_levels.poc:.2f} | VolRatio: {volume_ratio:.2f}"
        )

        # LONG değerlendirmesi
        if trend_result.is_bullish():
            signal = self._check_long(symbol, df, last_candle, prev_candle, vp_levels, trend_result, current_price, volume_ratio)
            if signal:
                self._last_signal_time[symbol] = current_time
                return signal

        # SHORT değerlendirmesi
        if trend_result.is_bearish():
            signal = self._check_short(symbol, df, last_candle, prev_candle, vp_levels, trend_result, current_price, volume_ratio)
            if signal:
                self._last_signal_time[symbol] = current_time
                return signal
        
        return None

    def _check_long(self, symbol, df, last, prev, vp, trend, price, vol_ratio) -> Optional[Signal]:
        poc = vp.poc
        
        # Kural 2: Fiyat POC'un üzerinde (veya çok yakınında) olmalı
        if price < poc * 0.995: 
            return None

        # Kural 4: Hacim filtresi
        if vol_ratio < 0.50:
            return None

        logger.info("✅ LONG sinyali üretildi: %s @ %.4f", symbol, price)
        return Signal(side="LONG", symbol=symbol, price=price, poc=poc, vah=vp.vah, val=vp.val, ema_fast=trend.ema_fast, ema_slow=trend.ema_slow, volume_ratio=vol_ratio)

    def _check_short(self, symbol, df, last, prev, vp, trend, price, vol_ratio) -> Optional[Signal]:
        poc = vp.poc
        
        # Kural 2: Fiyat POC'un altında (veya çok yakınında) olmalı
        if price > poc * 1.005: 
            return None

        # Kural 4: Hacim filtresi
        if vol_ratio < 0.50:
            return None

        logger.info("✅ SHORT sinyali üretildi: %s @ %.4f", symbol, price)
        return Signal(side="SHORT", symbol=symbol, price=price, poc=poc, vah=vp.vah, val=vp.val, ema_fast=trend.ema_fast, ema_slow=trend.ema_slow, volume_ratio=vol_ratio)