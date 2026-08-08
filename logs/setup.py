"""
logs/setup.py
=============
Merkezi loglama yapılandırması.

Her modül `logging.getLogger(__name__)` ile bu yapılandırmadan faydalanır.
Loglar hem konsola hem dönen dosyaya yazılır.
"""

import logging
import logging.handlers
import os
from pathlib import Path

from config import config, LogConfig


def setup_logging(cfg: LogConfig | None = None) -> None:
    """
    Uygulama genelinde loglama sistemini yapılandırır.

    Çağrı noktası: main.py içinde, tüm modüllerden önce.

    Parameters
    ----------
    cfg : LogConfig nesnesi (None → config singleton'dan alınır)
    """
    cfg = cfg or config.log

    # Log dizini oluştur
    log_dir = Path(cfg.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Kök logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, cfg.level.upper(), logging.INFO))

    # Formatlayıcı
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # --- Konsol handler ---
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # --- Dönen dosya handler (RotatingFileHandler) ---
    file_handler = logging.handlers.RotatingFileHandler(
        filename=cfg.log_file,
        maxBytes=cfg.max_bytes,
        backupCount=cfg.backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Mevcut handler'ları temizle (çift loglama önleme)
    if root_logger.handlers:
        root_logger.handlers.clear()

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Gürültülü kütüphaneleri sustur
    for noisy_lib in ("ccxt", "urllib3", "asyncio", "uvicorn.access"):
        logging.getLogger(noisy_lib).setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "Log sistemi hazır: %s (seviye=%s)", cfg.log_file, cfg.level
    )
