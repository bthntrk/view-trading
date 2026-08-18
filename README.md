# Volume Profile Trading System

A modular Python algorithmic trading system based on **Volume Profile (POC / VAH / VAL)** signals, with paper trading, backtesting, risk management and a FastAPI REST API.

The project is designed around clear separation between exchange connectivity, indicators, strategy logic, execution, risk management, persistence and backtesting.

> This repository is intended for paper trading, backtesting and software experimentation. It does not provide financial advice.

---

## Features

| Feature | Details |
|---|---|
| Strategy | Volume Profile (POC / VAH / VAL) + EMA trend filter |
| Execution | Paper trading |
| Exchange | Binance via CCXT |
| Symbols | BTC/USDT, ETH/USDT |
| Risk Management | 1% risk, 1.5% SL, 3% TP, minimum 1:2 risk/reward |
| Database | SQLite |
| API | FastAPI REST API |
| Backtesting | Historical strategy evaluation |

---

## Architecture

The system is split into independent modules so that strategy logic, execution, exchange access and risk management can evolve separately.

```text
project/
├── main.py
├── config.py
├── requirements.txt
│
├── api/
│   └── app.py
│
├── backtesting/
│   └── engine.py
│
├── database/
│   └── manager.py
│
├── exchange/
│   └── client.py
│
├── indicators/
│   ├── volume_profile.py
│   └── trend_filter.py
│
├── logs/
│   └── setup.py
│
├── paper_trading/
│   └── engine.py
│
├── risk_management/
│   └── manager.py
│
└── strategy/
    └── signal.py
