import asyncio
import httpx
from bs4 import BeautifulSoup
import sys
sys.path.append('crawler/src')
from roombeacon_crawler.sources.phongtro123.parsers.listing_parser import Phongtro123ListingParser

async def main():
    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
        r = await client.get("https://phongtro123.com/tinh-thanh/ho-chi-minh")
        parser = Phongtro123ListingParser()
        cards = parser.parse(r.text, "https://phongtro123.com/tinh-thanh/ho-chi-minh")
        for card in cards[:3]:
            print(f"ID: {card.listing_id}")
            print(f"Location: {card.location_raw!r}")
            print("---")

asyncio.run(main())
