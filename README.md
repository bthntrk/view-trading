# Volume Profile Trading Bot

Paper trading modu ile çalışan, Volume Profile (VRVP / SVP HD mantığı) tabanlı
profesyonel kripto para işlem botu.

---

## Özellikler

| Özellik | Detay |
|---|---|
| Strateji | Volume Profile (POC / VAH / VAL) + EMA trend filtresi |
| Mod | Paper Trading (sanal işlem) |
| Borsalar | Binance (CCXT) |
| Semboller | BTC/USDT, ETH/USDT |
| Risk Yönetimi | %1 risk, %1.5 SL, %3 TP, min. 1:2 RR |
| Veritabanı | SQLite |
| API | FastAPI (REST) |

---

## Kurulum

```bash
# 1. Depoyu klonla
git clone <repo-url>
cd project

# 2. Sanal ortam oluştur (Python 3.12+)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Bağımlılıkları yükle
pip install -r requirements.txt

# 4. API anahtarlarını ayarla (sadece veri çekme için gerekli)
export BINANCE_API_KEY="your_api_key"
export BINANCE_API_SECRET="your_api_secret"
```

---

## Kullanım

### Paper Trading Modu (varsayılan)

```bash
python main.py
```

### Backtest Modu

```bash
python main.py backtest
```

### API Sunucusu

Bot çalışırken otomatik olarak `http://localhost:8000` adresinde ayağa kalkar.

---

## API Endpoint'leri

| Endpoint | Metot | Açıklama |
|---|---|---|
| `/status` | GET | Bot durumu |
| `/positions` | GET | Açık pozisyonlar |
| `/trades` | GET | İşlem geçmişi |
| `/balance` | GET | Bakiye ve özet |
| `/signals` | GET | Son sinyaller |
| `/stats` | GET | Performans istatistikleri |
| `/start` | POST | Botu başlat |
| `/stop` | POST | Botu durdur |
| `/health` | GET | Sağlık kontrolü |

Swagger UI: `http://localhost:8000/docs`

---

## Klasör Yapısı

```
project/
├── main.py                  # Giriş noktası
├── config.py                # Tüm yapılandırmalar
├── requirements.txt
├── exchange/
│   └── client.py            # CCXT bağlantı istemcisi
├── strategy/
│   └── signal.py            # Strateji motoru
├── indicators/
│   ├── volume_profile.py    # POC / VAH / VAL hesaplama
│   └── trend_filter.py      # EMA-50 / EMA-200 trend filtresi
├── risk_management/
│   └── manager.py           # SL / TP / pozisyon büyüklüğü
├── paper_trading/
│   └── engine.py            # Sanal işlem sistemi
├── database/
│   └── manager.py           # SQLite yöneticisi
├── backtesting/
│   └── engine.py            # Geriye dönük test motoru
├── logs/
│   └── setup.py             # Log yapılandırması
└── api/
    └── app.py               # FastAPI uygulaması
```

---

## Strateji Kuralları

### LONG Sinyali

1. EMA-50 > EMA-200 (yükseliş trendi)
2. Fiyat POC'un üzerinde
3. Önceki mum POC'a dokunmuş + son mum yukarı kapanış
4. Son hacim > 20 mum hacim ortalaması

### SHORT Sinyali

1. EMA-50 < EMA-200 (düşüş trendi)
2. Fiyat POC'un altında
3. Önceki mum POC'a yükselmiş + son mum aşağı kapanış
4. Son hacim > 20 mum hacim ortalaması

---

## Yapılandırma

`config.py` içindeki dataclass'ları düzenleyerek tüm parametreleri değiştirebilirsiniz:

```python
# Örnek: Risk ayarlarını değiştir
config.risk.stop_loss_pct = 0.02    # %2 stop loss
config.risk.take_profit_pct = 0.04  # %4 take profit

# Volume Profile çözünürlüğünü artır
config.volume_profile.num_bins = 300
```

---

## Geliştirme Notları

- **SOLID prensipleri**: Her sınıf tek bir sorumluluğa sahip
- **Type Hints**: Tüm fonksiyonlarda tip belirteçleri kullanılmış
- **Docstrings**: Her modül, sınıf ve kritik metot belgelenmiş
- **Hata yönetimi**: Exchange hataları, veri eksiklikleri yakalanaharak loglanır
- **Asyncio**: Veri çekme ve API paralel çalışır
- **Production-ready logging**: Dönen dosya + konsol, seviye kontrolü

---

## Lisans

MIT
