"""
database/manager.py
===================
SQLite veritabanı yöneticisi.

İşlem geçmişini ve bakiye durumunu kalıcı olarak saklar.
Thread-safe, async uyumlu (aiofiles benzeri basit wrapper kullanılır).
"""

import asyncio
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Generator, List, Optional

from config import config, DatabaseConfig

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# DDL — Tablo tanımları
# ------------------------------------------------------------------

_CREATE_TRADES_TABLE = """
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT    NOT NULL,
    side            TEXT    NOT NULL,          -- LONG / SHORT
    entry_price     REAL    NOT NULL,
    exit_price      REAL,                      -- NULL → açık pozisyon
    stop_loss       REAL    NOT NULL,
    take_profit     REAL    NOT NULL,
    position_size   REAL    NOT NULL,
    risk_amount     REAL    NOT NULL,
    pnl             REAL,                      -- NULL → açık pozisyon
    status          TEXT    NOT NULL DEFAULT 'OPEN',  -- OPEN / CLOSED / STOPPED
    entry_time      TEXT    NOT NULL,
    exit_time       TEXT,
    notes           TEXT
);
"""

_CREATE_BALANCE_TABLE = """
CREATE TABLE IF NOT EXISTS balance_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    balance     REAL    NOT NULL,
    equity      REAL    NOT NULL,
    recorded_at TEXT    NOT NULL
);
"""

_CREATE_SIGNALS_TABLE = """
CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT    NOT NULL,
    side        TEXT    NOT NULL,
    price       REAL    NOT NULL,
    poc         REAL,
    vah         REAL,
    val         REAL,
    ema_fast    REAL,
    ema_slow    REAL,
    acted       INTEGER NOT NULL DEFAULT 0,   -- 0=görmezden gelindi, 1=işleme açıldı
    created_at  TEXT    NOT NULL
);
"""


# ------------------------------------------------------------------
# Yardımcı fonksiyonlar
# ------------------------------------------------------------------

def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------------
# Veritabanı Yöneticisi
# ------------------------------------------------------------------

class DatabaseManager:
    """
    SQLite üzerinden kalıcı depolama sağlayan sınıf.

    Bağlantı yönetimi için bağlam yöneticisi (context manager) kullanır.
    Tüm yazma işlemleri transaction içinde gerçekleşir.
    """

    def __init__(self, cfg: Optional[DatabaseConfig] = None) -> None:
        self._cfg = cfg or config.database
        self._db_path = Path(self._cfg.db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # Başlatma
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        """Tabloları oluşturur (yoksa)."""
        with self._get_conn() as conn:
            conn.execute(_CREATE_TRADES_TABLE)
            conn.execute(_CREATE_BALANCE_TABLE)
            conn.execute(_CREATE_SIGNALS_TABLE)
        logger.info("Veritabanı hazır: %s", self._db_path)

    @contextmanager
    def _get_conn(self) -> Generator[sqlite3.Connection, None, None]:
        """Thread-safe SQLite bağlantı context manager'ı."""
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # İşlem (Trade) işlemleri
    # ------------------------------------------------------------------

    def insert_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        position_size: float,
        risk_amount: float,
        notes: str = "",
    ) -> int:
        """Yeni işlem kaydı açar. Oluşturulan trade ID'sini döner."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO trades
                  (symbol, side, entry_price, stop_loss, take_profit,
                   position_size, risk_amount, status, entry_time, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)
                """,
                (symbol, side, entry_price, stop_loss, take_profit,
                 position_size, risk_amount, _now_utc(), notes),
            )
            trade_id = cursor.lastrowid
        logger.info("Trade kaydedildi: ID=%d %s %s @ %.4f",
                    trade_id, symbol, side, entry_price)
        return trade_id

    def close_trade(
        self,
        trade_id: int,
        exit_price: float,
        pnl: float,
        status: str = "CLOSED",
    ) -> None:
        """Açık bir işlemi kapatır (CLOSED veya STOPPED)."""
        with self._get_conn() as conn:
            conn.execute(
                """
                UPDATE trades
                SET exit_price=?, pnl=?, status=?, exit_time=?
                WHERE id=?
                """,
                (exit_price, pnl, status, _now_utc(), trade_id),
            )
        logger.info("Trade kapatıldı: ID=%d Çıkış=%.4f PnL=%.2f status=%s",
                    trade_id, exit_price, pnl, status)

    def get_open_trades(self) -> List[Dict]:
        """Açık pozisyonları listeler."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status='OPEN' ORDER BY entry_time DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_all_trades(self, limit: int = 100) -> List[Dict]:
        """Tüm işlem geçmişini döner."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM trades ORDER BY entry_time DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_trade_by_id(self, trade_id: int) -> Optional[Dict]:
        """ID'ye göre tek bir işlem döner."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM trades WHERE id=?", (trade_id,)
            ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Bakiye geçmişi
    # ------------------------------------------------------------------

    def record_balance(self, balance: float, equity: float) -> None:
        """Anlık bakiye ve özkaynağı kaydeder."""
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO balance_history (balance, equity, recorded_at) VALUES (?, ?, ?)",
                (balance, equity, _now_utc()),
            )

    def get_latest_balance(self) -> Optional[Dict]:
        """En son kaydedilen bakiye bilgisini döner."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM balance_history ORDER BY recorded_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Sinyal geçmişi
    # ------------------------------------------------------------------

    def insert_signal(
        self,
        symbol: str,
        side: str,
        price: float,
        poc: float,
        vah: float,
        val: float,
        ema_fast: float,
        ema_slow: float,
        acted: bool = False,
    ) -> int:
        """Üretilen sinyali kaydeder."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO signals
                  (symbol, side, price, poc, vah, val, ema_fast, ema_slow, acted, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (symbol, side, price, poc, vah, val, ema_fast, ema_slow,
                 int(acted), _now_utc()),
            )
            return cursor.lastrowid

    def get_recent_signals(self, limit: int = 50) -> List[Dict]:
        """Son N sinyali döner."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # İstatistik
    # ------------------------------------------------------------------

    def get_trade_stats(self) -> Dict:
        """Tüm kapalı işlemler için performans istatistiklerini hesaplar."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT pnl FROM trades WHERE status IN ('CLOSED', 'STOPPED')"
            ).fetchall()

        pnls = [r["pnl"] for r in rows if r["pnl"] is not None]
        if not pnls:
            return {}

        winners = [p for p in pnls if p > 0]
        losers = [p for p in pnls if p <= 0]

        return {
            "total_trades": len(pnls),
            "winners": len(winners),
            "losers": len(losers),
            "win_rate": len(winners) / len(pnls) if pnls else 0,
            "gross_profit": sum(winners),
            "gross_loss": sum(losers),
            "net_pnl": sum(pnls),
        }
