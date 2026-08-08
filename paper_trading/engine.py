"""
paper_trading/engine.py
========================
Sanal işlem (Paper Trading) motoru.

Gerçek emir göndermez; işlemleri veritabanında simüle eder.
Pozisyon yönetimi, PnL hesaplama ve bakiye güncellemelerini üstlenir.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from config import config, PaperTradingConfig
from database.manager import DatabaseManager
from risk_management.manager import RiskManager, RiskParameters
from strategy.signal import Signal

logger = logging.getLogger(__name__)

@dataclass
class Position:
    """Bellekte tutulan açık pozisyon kaydı."""
    trade_id: int
    symbol: str
    side: str
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size: float
    risk_amount: float
    peak_price: float = 0.0 # YENİ: Fiyatın gördüğü en yüksek/düşük seviyeyi tutar

    def unrealized_pnl(self, current_price: float) -> float:
        if self.side == "LONG":
            return (current_price - self.entry_price) * self.position_size
        return (self.entry_price - current_price) * self.position_size

    def should_stop(self, current_price: float) -> bool:
        if self.side == "LONG":
            return current_price <= self.stop_loss
        return current_price >= self.stop_loss

    def should_take_profit(self, current_price: float) -> bool:
        if self.side == "LONG":
            return current_price >= self.take_profit
        return current_price <= self.take_profit

    def __str__(self) -> str:
        return (
            f"[{self.side}] {self.symbol} | Entry={self.entry_price:.4f} "
            f"SL={self.stop_loss:.4f} TP={self.take_profit:.4f} Size={self.position_size:.6f}"
        )

class PaperTradingEngine:
    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        risk_manager: Optional[RiskManager] = None,
        cfg: Optional[PaperTradingConfig] = None,
    ) -> None:
        self._cfg = cfg or config.paper_trading
        self._db = db or DatabaseManager()
        self._risk = risk_manager or RiskManager()

        self._balance: float = self._cfg.initial_balance
        self._open_positions: Dict[int, Position] = {} 

        logger.info("Paper Trading başlatıldı | Başlangıç bakiyesi: %.2f USDT", self._balance)

    @property
    def balance(self) -> float:
        return self._balance

    @property
    def open_positions(self) -> List[Position]:
        return list(self._open_positions.values())

    @property
    def equity(self) -> float:
        return self._balance

    def open_position(self, signal: Signal) -> Optional[Position]:
        # Maksimum pozisyon kontrolü
        if len(self._open_positions) >= config.risk.max_open_positions:
            return None

        # Aynı sembol kontrolü
        for pos in self._open_positions.values():
            if pos.symbol == signal.symbol:
                return None

        # --- YENİ DİNAMİK MANTIK: %1 İlk Stop, %5 Nihai TP ---
        FIXED_AMOUNT_USD = 10.0
        INITIAL_STOP_PCT = 0.01   # %1 Zarar Kes
        TAKE_PROFIT_PCT = 0.05    # TP'yi %5'e çektik ki erken satmasın, trailing stop devreye girsin
        
        fixed_size = FIXED_AMOUNT_USD / signal.price
        
        if signal.side == "LONG":
            sl = signal.price * (1 - INITIAL_STOP_PCT)
            tp = signal.price * (1 + TAKE_PROFIT_PCT)
        else:
            sl = signal.price * (1 + INITIAL_STOP_PCT)
            tp = signal.price * (1 - TAKE_PROFIT_PCT)

        risk_params = RiskParameters(
            side=signal.side,
            entry_price=signal.price,
            stop_loss=sl,
            take_profit=tp,
            position_size=fixed_size,
            risk_amount=FIXED_AMOUNT_USD,
            rr_ratio=2.0
        )

        commission = signal.price * fixed_size * self._cfg.commission_pct
        if self._balance < (FIXED_AMOUNT_USD + commission):
            logger.warning("Bakiye yetersiz.")
            return None

        self._balance -= (FIXED_AMOUNT_USD + commission)

        trade_id = self._db.insert_trade(
            symbol=signal.symbol,
            side=signal.side,
            entry_price=risk_params.entry_price,
            stop_loss=risk_params.stop_loss,
            take_profit=risk_params.take_profit,
            position_size=risk_params.position_size,
            risk_amount=risk_params.risk_amount,
            notes=f"VP Sinyal | İzleyen Stop Aktif",
        )

        position = Position(
            trade_id=trade_id,
            symbol=signal.symbol,
            side=signal.side,
            entry_price=risk_params.entry_price,
            stop_loss=risk_params.stop_loss,
            take_profit=risk_params.take_profit,
            position_size=risk_params.position_size,
            risk_amount=risk_params.risk_amount,
            peak_price=signal.price, # Zirveyi giriş fiyatından başlatıyoruz
        )
        self._open_positions[trade_id] = position
        self._db.record_balance(self._balance, self._balance)

        logger.info("📈 Pozisyon açıldı: %s", position)
        return position

    def update_positions(self, prices: Dict[str, float]) -> List[Position]:
        closed: List[Position] = []
        TRAILING_STEP_PCT = 0.005 # Fiyat %0.5 geri çekilirse Stop patlar

        for trade_id, pos in list(self._open_positions.items()):
            price = prices.get(pos.symbol)
            
            if price is None:
                continue

            # --- İZLEYEN STOP (TRAILING STOP) MANTIĞI ---
            if pos.side == "LONG":
                # Fiyat yeni bir zirve yaptıysa
                if price > pos.peak_price:
                    pos.peak_price = price # Zirveyi güncelle
                    new_sl = price * (1 - TRAILING_STEP_PCT) # Yeni stop mesafesini hesapla
                    # Sadece stop'u yukarı çekebiliriz, aşağı düşüremeyiz
                    if new_sl > pos.stop_loss:
                        pos.stop_loss = new_sl
                        logger.debug("🔺 [%s] İzleyen Stop yukarı çekildi: %.4f", pos.symbol, new_sl)
            else: # SHORT
                # Fiyat yeni bir dip yaptıysa
                if price < pos.peak_price:
                    pos.peak_price = price
                    new_sl = price * (1 + TRAILING_STEP_PCT)
                    if new_sl < pos.stop_loss:
                        pos.stop_loss = new_sl
                        logger.debug("🔻 [%s] İzleyen Stop aşağı çekildi: %.4f", pos.symbol, new_sl)
            # --------------------------------------------

            if pos.should_stop(price):
                self._close_position(trade_id, price, "STOPPED")
                closed.append(pos)
            elif pos.should_take_profit(price):
                self._close_position(trade_id, price, "CLOSED")
                closed.append(pos)
        return closed

    def _close_position(self, trade_id: int, exit_price: float, status: str) -> None:
        pos = self._open_positions.pop(trade_id, None)
        if not pos: return

        commission = exit_price * pos.position_size * self._cfg.commission_pct
        if pos.side == "LONG":
            gross_pnl = (exit_price - pos.entry_price) * pos.position_size
        else:
            gross_pnl = (pos.entry_price - exit_price) * pos.position_size

        net_pnl = gross_pnl - commission
        self._balance += pos.risk_amount + net_pnl

        self._db.close_trade(trade_id, exit_price, net_pnl, status)
        self._db.record_balance(self._balance, self._balance)

        logger.info("✅ Pozisyon kapandı [%s] | PnL=%.2f$ | Bakiye=%.2f$", status, net_pnl, self._balance)

    def get_summary(self) -> Dict:
        stats = self._db.get_trade_stats()
        return {
            "balance": round(self._balance, 2),
            "open_positions": len(self._open_positions),
            "initial_balance": self._cfg.initial_balance,
            "total_pnl": round(self._balance - self._cfg.initial_balance, 2),
            **stats,
        }