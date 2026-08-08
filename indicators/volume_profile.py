"""
indicators/volume_profile.py
============================
Volume Profile hesaplama motoru.

VRVP (Visible Range Volume Profile) ve SVP HD mantığına yakın çalışır:
- Fiyat aralığını eşit bölmelere (bin) ayırır
- Her bölmeye düşen hacmi hesaplar
- POC, VAH, VAL seviyelerini üretir
"""

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from config import config, VolumeProfileConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VolumeProfileLevels:
    """
    Volume Profile çıktısı.

    Attributes
    ----------
    poc : float
        Point of Control — en yüksek hacmin olduğu fiyat seviyesi.
    vah : float
        Value Area High — değer alanının üst sınırı.
    val : float
        Value Area Low — değer alanının alt sınırı.
    profile : pd.Series
        Fiyat bölmesi → hacim haritası (index=fiyat, values=hacim).
    """
    poc: float
    vah: float
    val: float
    profile: pd.Series

    def __str__(self) -> str:
        return (
            f"VolumeProfile | POC={self.poc:.4f} "
            f"VAH={self.vah:.4f} VAL={self.val:.4f}"
        )


class VolumeProfileCalculator:
    """
    OHLCV verisinden Volume Profile hesaplayan sınıf.

    TradingView VRVP / SVP HD mantığı:
    - Her mum için, mumun high-low aralığını num_bins bölmeye dağıtır.
    - Her bölmeye düşen hacim = mum hacmi / bölme sayısı (uniform dağılım).
    - Daha gelişmiş versiyonlarda TPO (Time Price Opportunity) kullanılabilir.
    """

    def __init__(self, cfg: Optional[VolumeProfileConfig] = None) -> None:
        self._cfg = cfg or config.volume_profile

    # ------------------------------------------------------------------
    # Ana hesaplama
    # ------------------------------------------------------------------

    def calculate(
        self,
        df: pd.DataFrame,
        lookback_bars: Optional[int] = None,
    ) -> VolumeProfileLevels:
        """
        Verilen OHLCV DataFrame'inden Volume Profile hesaplar.

        Parameters
        ----------
        df           : OHLCV verisi (index=timestamp)
        lookback_bars: Kullanılacak son mum sayısı (None → config.lookback_days)

        Returns
        -------
        VolumeProfileLevels
        """
        data = self._slice_data(df, lookback_bars)
        profile = self._build_profile(data)
        poc, vah, val = self._extract_levels(profile)

        levels = VolumeProfileLevels(
            poc=poc, vah=vah, val=val, profile=profile
        )
        logger.debug("Volume Profile hesaplandı: %s", levels)
        return levels

    # ------------------------------------------------------------------
    # Yardımcı metodlar
    # ------------------------------------------------------------------

    def _slice_data(
        self, df: pd.DataFrame, lookback_bars: Optional[int]
    ) -> pd.DataFrame:
        """Veriyi geri bakış penceresine göre keser."""
        if lookback_bars is not None:
            return df.tail(lookback_bars)

        # Gün bazlı geri bakış
        if not df.empty:
            cutoff = df.index[-1] - pd.Timedelta(days=self._cfg.lookback_days)
            return df[df.index >= cutoff]
        return df

    def _build_profile(self, df: pd.DataFrame) -> pd.Series:
        """
        Her fiyat bölmesi için toplam hacmi hesaplar.

        Yöntem:
        -------
        Her mumun [low, high] aralığını num_bins fiyat kutusuna dağıtır.
        Mum hacmini, aralıktaki kutu sayısına eşit olarak böler.
        """
        price_min: float = df["low"].min()
        price_max: float = df["high"].max()
        num_bins: int = self._cfg.num_bins

        # Fiyat bölmeleri (bin kenarları)
        bin_edges = np.linspace(price_min, price_max, num_bins + 1)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0
        volume_per_bin = np.zeros(num_bins, dtype=np.float64)

        for _, row in df.iterrows():
            low, high, vol = row["low"], row["high"], row["volume"]
            if high == low:
                # Doji mum → hacim ortaya atar
                idx = np.searchsorted(bin_edges, (low + high) / 2.0, side="right") - 1
                idx = int(np.clip(idx, 0, num_bins - 1))
                volume_per_bin[idx] += vol
                continue

            # Mumun kapsadığı bin aralığını bul
            lo_idx = int(np.searchsorted(bin_edges, low, side="left"))
            hi_idx = int(np.searchsorted(bin_edges, high, side="right"))
            lo_idx = max(0, lo_idx - 1)
            hi_idx = min(num_bins, hi_idx)

            span = hi_idx - lo_idx
            if span == 0:
                span = 1
            vol_per_slice = vol / span
            volume_per_bin[lo_idx:hi_idx] += vol_per_slice

        profile = pd.Series(volume_per_bin, index=bin_centers)
        return profile

    def _extract_levels(
        self, profile: pd.Series
    ) -> tuple[float, float, float]:
        """
        POC, VAH ve VAL seviyelerini profil üzerinden hesaplar.

        Value Area mantığı (TradingView uyumlu):
        Toplam hacmin %68'ini kapsayan en yüksek yoğunluklu fiyat bandı.
        """
        total_volume: float = profile.sum()
        target_volume: float = total_volume * self._cfg.value_area_pct

        # POC: en yüksek hacimli fiyat seviyesi
        poc_price: float = float(profile.idxmax())

        # Value Area genişletme: POC'tan dışa doğru
        sorted_profile = profile.sort_values(ascending=False)
        cumulative = 0.0
        value_area_prices = []

        for price, vol in sorted_profile.items():
            cumulative += vol
            value_area_prices.append(float(price))
            if cumulative >= target_volume:
                break

        vah: float = max(value_area_prices)
        val: float = min(value_area_prices)

        return poc_price, vah, val
