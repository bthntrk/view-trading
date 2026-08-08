"""
api/app.py
===========
FastAPI tabanlı REST API.

Bot durumu, pozisyonlar, işlem geçmişi ve kontrol komutlarını sunar.
"""

import logging
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import config
from database.manager import DatabaseManager
from paper_trading.engine import PaperTradingEngine

logger = logging.getLogger(__name__)

# FastAPI uygulaması
app = FastAPI(
    title="Volume Profile Trading Bot API",
    description="Paper trading botu için REST API",
    version="1.0.0",
)

# CORS — geliştirme ortamı için tüm originlere izin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Uygulama durumu (main.py tarafından enjekte edilir)
_db: DatabaseManager = None        # type: ignore[assignment]
_pt_engine: PaperTradingEngine = None  # type: ignore[assignment]
_bot_running: bool = False


def init_api(db: DatabaseManager, pt_engine: PaperTradingEngine) -> None:
    """Main.py tarafından çağrılır; bağımlılıkları enjekte eder."""
    global _db, _pt_engine
    _db = db
    _pt_engine = pt_engine
    logger.info("API bağımlılıkları enjekte edildi.")


# ------------------------------------------------------------------
# Yardımcı
# ------------------------------------------------------------------

def _check_initialized() -> None:
    if _db is None or _pt_engine is None:
        raise HTTPException(status_code=503, detail="Bot henüz başlatılmadı.")


# ------------------------------------------------------------------
# Endpoint'ler
# ------------------------------------------------------------------

@app.get("/status", summary="Bot durumunu göster")
async def get_status() -> Dict[str, Any]:
    """
    Botun genel durumunu döner.

    - running   : Bot çalışıyor mu?
    - symbols   : İzlenen semboller
    - timeframe : Zaman dilimi
    """
    return {
        "running": _bot_running,
        "symbols": config.symbol.symbols,
        "timeframe": config.symbol.timeframe,
        "paper_trading": True,
        "initial_balance": config.paper_trading.initial_balance,
    }


@app.get("/positions", summary="Açık pozisyonları listele")
async def get_positions() -> List[Dict[str, Any]]:
    """Bellekteki açık pozisyonları döner."""
    _check_initialized()
    positions = _pt_engine.open_positions
    return [
        {
            "trade_id": p.trade_id,
            "symbol": p.symbol,
            "side": p.side,
            "entry_price": p.entry_price,
            "stop_loss": p.stop_loss,
            "take_profit": p.take_profit,
            "position_size": p.position_size,
            "risk_amount": p.risk_amount,
        }
        for p in positions
    ]


@app.get("/trades", summary="İşlem geçmişini listele")
async def get_trades(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Veritabanındaki son N işlemi döner.

    Query param: limit (varsayılan 50)
    """
    _check_initialized()
    trades = _db.get_all_trades(limit=limit)
    return trades


@app.get("/balance", summary="Bakiye bilgisi")
async def get_balance() -> Dict[str, Any]:
    """Mevcut bakiye ve performans özetini döner."""
    _check_initialized()
    summary = _pt_engine.get_summary()
    return summary


@app.post("/start", summary="Botu başlat")
async def start_bot() -> Dict[str, str]:
    """
    Botu başlatır.
    Ana döngü main.py tarafından çalıştırılır; bu endpoint sinyal gönderir.
    """
    global _bot_running
    if _bot_running:
        raise HTTPException(status_code=409, detail="Bot zaten çalışıyor.")
    _bot_running = True
    logger.info("Bot başlatma isteği alındı (API).")
    return {"status": "started", "message": "Bot başlatıldı."}


@app.post("/stop", summary="Botu durdur")
async def stop_bot() -> Dict[str, str]:
    """Çalışan botu durdurur."""
    global _bot_running
    if not _bot_running:
        raise HTTPException(status_code=409, detail="Bot zaten durmuş.")
    _bot_running = False
    logger.info("Bot durdurma isteği alındı (API).")
    return {"status": "stopped", "message": "Bot durduruldu."}


@app.get("/signals", summary="Son sinyaller")
async def get_signals(limit: int = 20) -> List[Dict[str, Any]]:
    """Son N üretilen sinyali döner."""
    _check_initialized()
    return _db.get_recent_signals(limit=limit)


@app.get("/stats", summary="Performans istatistikleri")
async def get_stats() -> Dict[str, Any]:
    """Tüm kapalı işlemlere ait performans istatistiklerini döner."""
    _check_initialized()
    return _db.get_trade_stats()


@app.get("/health", summary="Sağlık kontrolü")
async def health_check() -> Dict[str, str]:
    """Kubernetes / Docker için basit sağlık endpoint'i."""
    return {"status": "ok"}
