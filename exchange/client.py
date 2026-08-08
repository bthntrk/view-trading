import logging
import pandas as pd
import asyncio
import aiohttp

logger = logging.getLogger(__name__)

class ExchangeClient:
    def __init__(self, cfg=None) -> None:
        # Sadece senin erişebildiğin o özel Testnet URL'sini kullanıyoruz
        self.base_url = "https://testnet.binancefuture.com/fapi/v1/klines"
        self.session = None

    async def connect(self) -> None:
        # Aiohttp session başlatıyoruz (ccxt'ye gerek kalmadı)
        self.session = aiohttp.ClientSession()
        logger.info("CANLI MOD: Binance Futures Testnet API'ye başarıyla bağlanıldı.")

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 500) -> pd.DataFrame:
        # Botumuz 'BTC/USDT' istiyor ama Binance URL'si 'BTCUSDT' bekler.
        # Bu yüzden aradaki '/' işaretini kaldırıyoruz.
        formatted_symbol = symbol.replace("/", "")
        
        params = {
            "symbol": formatted_symbol,
            "interval": timeframe,
            "limit": limit
        }
        
        try:
            # Doğrudan senin bulduğun URL'ye istek atıyoruz
            async with self.session.get(self.base_url, params=params) as response:
                response.raise_for_status() # Hata varsa yakala
                data = await response.json()
                
                # Binance Klines formatını pandas DataFrame'e çeviriyoruz
                columns = [
                    'timestamp', 'open', 'high', 'low', 'close', 'volume', 
                    'close_time', 'quote_asset_volume', 'number_of_trades', 
                    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
                ]
                df = pd.DataFrame(data, columns=columns)
                
                # Sadece strateji motorunun ihtiyaç duyduğu temel sütunları filtrele
                df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
                
                # Verileri metin (string) yerine ondalık sayıya (float) çevir
                df = df.astype(float)
                
                # Zaman damgasını (timestamp) milisaniyeden okunabilir tarihe çevir ve index yap
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('timestamp', inplace=True)
                
                return df
        except Exception as e:
            logger.error("Veri çekilemedi [%s]: %s", symbol, e)
            return pd.DataFrame() # Botun çökmemesi için boş DataFrame dön

    async def fetch_multiple_ohlcv(self, symbols: list, timeframe: str = "1h", limit: int = 500) -> dict:
        # Tüm pariteleri eşzamanlı (asenkron) olarak çek
        results = []
        for symbol in symbols:
            df = await self.fetch_ohlcv(symbol, timeframe, limit)
            results.append(df)
            await asyncio.sleep(0.2)
        return dict(zip(symbols, results))


    async def close(self) -> None:
        if self.session:
            await self.session.close()
        logger.info("Testnet borsa bağlantısı kapatıldı.")