"""
config.py
=========
Merkezi yapılandırma dosyası.
Tüm sistem parametreleri buradan yönetilir.
"""

from dataclasses import dataclass, field
from typing import List
import os


# ---------------------------------------------------------------------------
# Exchange Ayarları
# ---------------------------------------------------------------------------
@dataclass
class ExchangeConfig:
    """Borsa bağlantı ayarları."""
    name: str = "binance"
    api_key: str = ""
    api_secret: str = ""
    testnet: bool = False        # True → testnet, False → canlı
    rate_limit: bool = True       # CCXT rate limiter aktif
    timeout: int = 30_000         # ms


# ---------------------------------------------------------------------------
# Sembol Ayarları
# ---------------------------------------------------------------------------
@dataclass
class SymbolConfig:
    """İşlem yapılacak semboller."""
    symbols: List[str] = field(default_factory=lambda: [
        'BTC/USDT', 'ETH/USDT', 
    
    # Yüksek Volatilite (Hızlı hareket edenler)
        'SOL/USDT', 'BNB/USDT', 'XRP/USDT', 'ADA/USDT', 
        'AVAX/USDT', 'DOGE/USDT', 'DOT/USDT', 'LINK/USDT', 
        'MATIC/USDT', 'NEAR/USDT', 'FTM/USDT', 'ARB/USDT'
        ])
    timeframe: str = "5m"         # OHLCV zaman dilimi
    ohlcv_limit: int = 500        # Çekilecek mum sayısı


# ---------------------------------------------------------------------------
# Volume Profile Ayarları
# ---------------------------------------------------------------------------
@dataclass
class VolumeProfileConfig:
    """Volume Profile hesaplama parametreleri."""
    lookback_days: int = 30       # Kaç günlük veri kullanılacak
    num_bins: int = 200           # Fiyat seviyeleri (VRVP çözünürlüğü)
    value_area_pct: float = 0.68  # Value Area = %68 hacim


# ---------------------------------------------------------------------------
# Trend Filtresi Ayarları
# ---------------------------------------------------------------------------
@dataclass
class TrendConfig:
    """EMA tabanlı trend filtresi parametreleri."""
    ema_fast: int = 50
    ema_slow: int = 200


# ---------------------------------------------------------------------------
# Strateji Ayarları
# ---------------------------------------------------------------------------
@dataclass
class StrategyConfig:
    """Sinyal üretim parametreleri."""
    volume_ma_period: int = 20    # Hacim ortalama periyodu
    poc_touch_tolerance: float = 0.005  # POC dokunuş toleransı (%0.2)


# ---------------------------------------------------------------------------
# Risk Yönetimi Ayarları
# ---------------------------------------------------------------------------
@dataclass
class RiskConfig:
    """Risk ve pozisyon yönetimi parametreleri."""
    risk_pct: float = 0.01        # Bakiyenin %1'i riske girer
    stop_loss_pct: float = 0.015  # Stop Loss %1.5
    take_profit_pct: float = 0.03 # Take Profit %3
    min_rr_ratio: float = 2.0     # Minimum Risk/Kazanç oranı
    max_open_positions: int = 20   # Aynı anda max açık pozisyon


# ---------------------------------------------------------------------------
# Paper Trading Ayarları
# ---------------------------------------------------------------------------
@dataclass
class PaperTradingConfig:
    """Sanal işlem sistemi parametreleri."""
    initial_balance: float = 10_000.0   # USDT
    commission_pct: float = 0.001       # %0.1 komisyon (Binance maker)


# ---------------------------------------------------------------------------
# Veritabanı Ayarları
# ---------------------------------------------------------------------------
@dataclass
class DatabaseConfig:
    """SQLite veritabanı ayarları."""
    db_path: str = "database/trading_bot.db"


# ---------------------------------------------------------------------------
# Backtest Ayarları
# ---------------------------------------------------------------------------
@dataclass
class BacktestConfig:
    """Geriye dönük test parametreleri."""
    lookback_days: int = 365      # 1 yıllık veri
    initial_balance: float = 10_000.0
    commission_pct: float = 0.001


# ---------------------------------------------------------------------------
# Log Ayarları
# ---------------------------------------------------------------------------
@dataclass
class LogConfig:
    """Loglama sistemi ayarları."""
    log_dir: str = "logs"
    log_file: str = "logs/trading_bot.log"
    level: str = "INFO"
    max_bytes: int = 10 * 1024 * 1024   # 10 MB
    backup_count: int = 5


# ---------------------------------------------------------------------------
# API Ayarları
# ---------------------------------------------------------------------------
@dataclass
class APIConfig:
    """FastAPI sunucu ayarları."""
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False


# ---------------------------------------------------------------------------
# Ana Yapılandırma
# ---------------------------------------------------------------------------
@dataclass
class AppConfig:
    """Uygulamanın tüm yapılandırmasını birleştiren ana sınıf."""
    exchange: ExchangeConfig = field(default_factory=ExchangeConfig)
    symbol: SymbolConfig = field(default_factory=SymbolConfig)
    volume_profile: VolumeProfileConfig = field(default_factory=VolumeProfileConfig)
    trend: TrendConfig = field(default_factory=TrendConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    paper_trading: PaperTradingConfig = field(default_factory=PaperTradingConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    log: LogConfig = field(default_factory=LogConfig)
    api: APIConfig = field(default_factory=APIConfig)


# Singleton yapılandırma nesnesi — tüm modüller bu nesneyi import eder
config = AppConfig()
