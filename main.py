"""
main.py
=======
Uygulama giriş noktası.

Tüm modülleri bir araya getirir:
- Exchange bağlantısı
- Strateji motoru
- Paper trading
- Veritabanı
- FastAPI sunucu (arka planda)
- Ana işlem döngüsü (asyncio)
"""

import asyncio
import logging
import signal
import sys
from typing import Dict

import uvicorn

from config import config
from logs.setup import setup_logging
from exchange.client import ExchangeClient
from strategy.signal import StrategyEngine
from paper_trading.engine import PaperTradingEngine
from database.manager import DatabaseManager
from backtesting.engine import BacktestEngine
from api.app import app, init_api

# Log sistemi en başta başlatılmalı
setup_logging()
logger = logging.getLogger(__name__)


# ===========================================================================
# Bot ana sınıfı
# ===========================================================================

class TradingBot:
    """
    Tüm bileşenleri orkestre eden ana bot sınıfı.

    Sorumluluklar:
    --------------
    - Exchange'den periyodik veri çekme
    - Strateji sinyali değerlendirme
    - Paper trading motoruna sinyal iletme
    - Açık pozisyonların SL/TP takibi
    - API sunucusunu arka planda çalıştırma
    """

    POLL_INTERVAL_SECONDS: int = 60  # Her N saniyede bir döngü

    def __init__(self) -> None:
        self._exchange = ExchangeClient()
        self._strategy = StrategyEngine()
        self._db = DatabaseManager()
        self._pt_engine = PaperTradingEngine(db=self._db)
        self._running: bool = False

        # API bağımlılık enjeksiyonu
        init_api(self._db, self._pt_engine)

    # ------------------------------------------------------------------
    # Yaşam döngüsü
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Botu başlatır; exchange bağlantısı kurar ve döngüyü açar."""
        logger.info("=" * 60)
        logger.info("  Volume Profile Trading Bot başlatılıyor...")
        logger.info("  Paper Trading MOD — gerçek emir GÖNDERİLMEZ")
        logger.info("  Semboller: %s", config.symbol.symbols)
        logger.info("  Zaman dilimi: %s", config.symbol.timeframe)
        logger.info("=" * 60)

        await self._exchange.connect()
        self._running = True

        # Başlangıç bakiyesini kaydet
        self._db.record_balance(
            self._pt_engine.balance,
            self._pt_engine.balance
        )

        await self._main_loop()

    async def stop(self) -> None:
        """Botu düzgünce kapatır."""
        logger.info("Bot kapatılıyor...")
        self._running = False
        await self._exchange.close()
        logger.info("Bot kapatıldı.")

    # ------------------------------------------------------------------
    # Ana döngü
    # ------------------------------------------------------------------

    async def _main_loop(self) -> None:
        """
        Periyodik olarak:
        1. OHLCV verisini çeker
        2. Sinyalleri değerlendirir
        3. Açık pozisyonları günceller
        4. Döngüyü bekler
        """
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                logger.error("Ana döngü hatası: %s", exc, exc_info=True)

            logger.debug("Sonraki kontrol: %ds sonra", self.POLL_INTERVAL_SECONDS)
            await asyncio.sleep(self.POLL_INTERVAL_SECONDS)

    async def _tick(self) -> None:
        """Tek bir döngü iterasyonu."""
        # 1. Veri çek
        ohlcv_data = await self._exchange.fetch_multiple_ohlcv(
            symbols=config.symbol.symbols,
            timeframe=config.symbol.timeframe,
            limit=config.symbol.ohlcv_limit,
        )

        if not ohlcv_data:
            logger.warning("Hiç veri çekilemedi, döngü atlanıyor.")
            return

        # 2. Güncel fiyatları topla (SL/TP güncellemesi için)
        current_prices: Dict[str, float] = {
            symbol: float(df.iloc[-1]["close"])
            for symbol, df in ohlcv_data.items()
        }

        # 3. Açık pozisyonları güncelle
        closed = self._pt_engine.update_positions(current_prices)
        if closed:
            logger.info("%d pozisyon kapandı.", len(closed))

        # 4. Sinyal değerlendirmesi
        for symbol, df in ohlcv_data.items():
            signal = self._strategy.evaluate(symbol, df)

            if signal:
                # Sinyali kaydet
                self._db.insert_signal(
                    symbol=signal.symbol,
                    side=signal.side,
                    price=signal.price,
                    poc=signal.poc,
                    vah=signal.vah,
                    val=signal.val,
                    ema_fast=signal.ema_fast,
                    ema_slow=signal.ema_slow,
                    acted=True,
                )

                # Paper trade aç
                position = self._pt_engine.open_position(signal)
                if position:
                    logger.info("Yeni pozisyon: %s", position)
                else:
                    logger.debug("Pozisyon açılamadı: %s", signal.symbol)

        # 5. Özet logla
        summary = self._pt_engine.get_summary()
        logger.info(
            "Özet | Bakiye=%.2f$ | Açık=%d | NetPnL=%.2f$",
            summary["balance"],
            summary["open_positions"],
            summary.get("net_pnl", 0.0),
        )


# ===========================================================================
# Backtest komutu
# ===========================================================================

async def run_backtest() -> None:
    """Backtest modunu çalıştırır."""
    exchange = ExchangeClient()
    await exchange.connect()

    bt_engine = BacktestEngine()

    for symbol in config.symbol.symbols:
        logger.info("Backtest verisi çekiliyor: %s", symbol)
        # 1 yıl ≈ 8760 saatlik mum (1h timeframe)
        limit = min(config.backtest.lookback_days * 24, 1000)
        df = await exchange.fetch_ohlcv(
            symbol,
            timeframe=config.symbol.timeframe,
            limit=limit,
        )
        result = bt_engine.run(symbol, df)
        result.print_summary()

    await exchange.close()


# ===========================================================================
# Uygulama başlatma
# ===========================================================================

async def _run_api_server() -> None:
    """FastAPI sunucusunu asyncio task olarak çalıştırır."""
    server_config = uvicorn.Config(
        app=app,
        host=config.api.host,
        port=config.api.port,
        log_level="warning",   # uvicorn kendi loglarını bastır
    )
    server = uvicorn.Server(server_config)
    await server.serve()


async def main() -> None:
    """Async giriş noktası."""
    mode = sys.argv[1] if len(sys.argv) > 1 else "bot"

    if mode == "backtest":
        await run_backtest()
        return

    # Bot + API birlikte başlat
    bot = TradingBot()

    # Graceful shutdown için sinyal yakalama
    loop = asyncio.get_event_loop()

    def _shutdown(sig_name: str) -> None:
        logger.info("Kapatma sinyali alındı: %s", sig_name)
        loop.create_task(bot.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: _shutdown(s.name))
        except NotImplementedError:
            pass  # Windows sinyal desteği sınırlı

    # Bot ve API'yi paralel çalıştır
    await asyncio.gather(
        bot.start(),
        _run_api_server(),
    )


if __name__ == "__main__":
    asyncio.run(main())
