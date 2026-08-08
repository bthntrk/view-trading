"""
indicators/trend_filter.py
===========================
EMA tabanlı trend filtresi.

EMA50 > EMA200 → Yükseliş trendi (sadece LONG)
EMA50 < EMA200 → Düşüş trendi  (sadece SHORT)
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd

from config import config, TrendConfig

logger = logging.getLogger(__name__)


class Trend(str, Enum):
    """Piyasa trend yönü."""
    BULLISH = "BULLISH"   # EMA50 > EMA200
    BEARISH = "BEARISH"   # EMA50 < EMA200
    NEUTRAL = "NEUTRAL"   # EMA'lar kesişiyor / yetersiz veri


@dataclass(frozen=True)
class TrendResult:
    """
    Trend filtresi çıktısı.

    Attributes
    ----------
    trend     : Tespit edilen trend yönü.
    ema_fast  : Son mumun EMA-50 değeri.
    ema_slow  : Son mumun EMA-200 değeri.
    """
    trend: Trend
    ema_fast: float
    ema_slow: float

    def is_bullish(self) -> bool:
        return self.trend == Trend.BULLISH

    def is_bearish(self) -> bool:
        return self.trend == Trend.BEARISH

    def __str__(self) -> str:
        return (
            f"Trend={self.trend.value} | "
            f"EMA{config.trend.ema_fast}={self.ema_fast:.4f} "
            f"EMA{config.trend.ema_slow}={self.ema_slow:.4f}"
        )


class TrendFilter:
    """
    EMA çapraz trend filtresini uygulayan sınıf.

    Kullanım:
    ---------
    >>> tf = TrendFilter()
    >>> result = tf.calculate(ohlcv_df)
    >>> if result.is_bullish():
    ...     # sadece LONG sinyalleri değerlendir
    """

    def __init__(self, cfg: Optional[TrendConfig] = None) -> None:
        self._cfg = cfg or config.trend

    def calculate(self, df: pd.DataFrame) -> TrendResult:
        """
        EMA değerlerini ve trend yönünü hesaplar.

        Parameters
        ----------
        df : close sütunu içeren OHLCV DataFrame

        Returns
        -------
        TrendResult
        """
        min_required = self._cfg.ema_slow + 1
        if len(df) < min_required:
            logger.warning(
                "Trend hesabı için yetersiz veri: %d/%d mum",
                len(df), min_required
            )
            return TrendResult(
                trend=Trend.NEUTRAL,
                ema_fast=float("nan"),
                ema_slow=float("nan"),
            )

        ema_fast_series = df["close"].ewm(
            span=self._cfg.ema_fast, adjust=False
        ).mean()
        ema_slow_series = df["close"].ewm(
            span=self._cfg.ema_slow, adjust=False
        ).mean()

        ema_fast_val = float(ema_fast_series.iloc[-1])
        ema_slow_val = float(ema_slow_series.iloc[-1])

        if ema_fast_val > ema_slow_val:
            trend = Trend.BULLISH
        elif ema_fast_val < ema_slow_val:
            trend = Trend.BEARISH
        else:
            trend = Trend.NEUTRAL

        result = TrendResult(
            trend=trend,
            ema_fast=ema_fast_val,
            ema_slow=ema_slow_val,
        )
        logger.debug("Trend hesaplandı: %s", result)
        return result

    def get_full_ema_series(
        self, df: pd.DataFrame
    ) -> tuple[pd.Series, pd.Series]:
        """
        Backtest için tüm EMA serilerini döner.

        Returns
        -------
        (ema_fast_series, ema_slow_series)
        """
        ema_fast = df["close"].ewm(span=self._cfg.ema_fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=self._cfg.ema_slow, adjust=False).mean()
        return ema_fast, ema_slow
