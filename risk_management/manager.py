"""
risk_management/manager.py
===========================
Risk yönetimi ve pozisyon büyüklüğü hesaplama modülü.

- Stop Loss ve Take Profit seviyelerini otomatik hesaplar
- Risk/Kazanç oranı kontrolü yapar
- Pozisyon büyüklüğünü (lot) bakiyeye göre belirler
"""

import logging
from dataclasses import dataclass
from typing import Literal, Optional

from config import config, RiskConfig

logger = logging.getLogger(__name__)

Side = Literal["LONG", "SHORT"]


@dataclass(frozen=True)
class RiskParameters:
    """
    Tek bir işlem için hesaplanmış risk parametreleri.

    Attributes
    ----------
    entry_price    : Giriş fiyatı
    stop_loss      : Stop loss fiyatı
    take_profit    : Take profit fiyatı
    position_size  : İşlem miktarı (baz para birimi)
    risk_amount    : Riske edilen USDT miktarı
    rr_ratio       : Risk/Kazanç oranı
    side           : LONG veya SHORT
    """
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size: float
    risk_amount: float
    rr_ratio: float
    side: Side

    def __str__(self) -> str:
        return (
            f"[{self.side}] Entry={self.entry_price:.4f} "
            f"SL={self.stop_loss:.4f} TP={self.take_profit:.4f} "
            f"Size={self.position_size:.6f} "
            f"Risk={self.risk_amount:.2f}$ RR={self.rr_ratio:.2f}"
        )


class RiskManager:
    """
    Her işlem için risk parametrelerini hesaplayan sınıf.

    Kurallar:
    ---------
    - LONG  : SL = entry * (1 - sl_pct), TP = entry * (1 + tp_pct)
    - SHORT : SL = entry * (1 + sl_pct), TP = entry * (1 - tp_pct)
    - Pozisyon büyüklüğü = risk_amount / stop_distance
    - RR oranı minimum config.risk.min_rr_ratio olmalı
    """

    def __init__(self, cfg: Optional[RiskConfig] = None) -> None:
        self._cfg = cfg or config.risk

    # ------------------------------------------------------------------
    # Ana hesaplama
    # ------------------------------------------------------------------

    def calculate(
        self,
        side: Side,
        entry_price: float,
        balance: float,
        sl_pct: Optional[float] = None,
        tp_pct: Optional[float] = None,
    ) -> Optional[RiskParameters]:
        """
        İşlem için risk parametrelerini hesaplar.

        Parameters
        ----------
        side        : "LONG" veya "SHORT"
        entry_price : Planlanan giriş fiyatı
        balance     : Mevcut bakiye (USDT)
        sl_pct      : Özel stop loss yüzdesi (None → config'den alınır)
        tp_pct      : Özel take profit yüzdesi (None → config'den alınır)

        Returns
        -------
        RiskParameters veya None (RR oranı yetersizse)
        """
        sl_pct = sl_pct or self._cfg.stop_loss_pct
        tp_pct = tp_pct or self._cfg.take_profit_pct

        stop_loss, take_profit = self._compute_levels(
            side, entry_price, sl_pct, tp_pct
        )
        rr_ratio = self._compute_rr(side, entry_price, stop_loss, take_profit)

        if rr_ratio < self._cfg.min_rr_ratio:
            logger.warning(
                "RR oranı yetersiz: %.2f < %.2f — işlem atlandı",
                rr_ratio,
                self._cfg.min_rr_ratio,
            )
            return None

        risk_amount = balance * self._cfg.risk_pct
        stop_distance = abs(entry_price - stop_loss)

        if stop_distance == 0:
            logger.error("Stop distance sıfır — işlem hesaplanamadı.")
            return None

        position_size = risk_amount / stop_distance

        params = RiskParameters(
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size,
            risk_amount=risk_amount,
            rr_ratio=rr_ratio,
            side=side,
        )
        logger.info("Risk parametreleri hesaplandı: %s", params)
        return params

    # ------------------------------------------------------------------
    # Yardımcı metodlar
    # ------------------------------------------------------------------

    def _compute_levels(
        self,
        side: Side,
        entry: float,
        sl_pct: float,
        tp_pct: float,
    ) -> tuple[float, float]:
        """Stop loss ve take profit fiyatlarını hesaplar."""
        if side == "LONG":
            stop_loss = entry * (1 - sl_pct)
            take_profit = entry * (1 + tp_pct)
        else:  # SHORT
            stop_loss = entry * (1 + sl_pct)
            take_profit = entry * (1 - tp_pct)
        return stop_loss, take_profit

    def _compute_rr(
        self,
        side: Side,
        entry: float,
        stop_loss: float,
        take_profit: float,
    ) -> float:
        """Risk/Kazanç oranını hesaplar."""
        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        if risk == 0:
            return 0.0
        return reward / risk

    def validate_balance(self, balance: float, risk_amount: float) -> bool:
        """Bakiyenin riski karşılayıp karşılamadığını kontrol eder."""
        if balance < risk_amount:
            logger.warning(
                "Yetersiz bakiye: %.2f < %.2f (risk miktarı)",
                balance, risk_amount
            )
            return False
        return True
