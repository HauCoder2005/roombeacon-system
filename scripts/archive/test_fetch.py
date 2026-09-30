import asyncio
import httpx
from bs4 import BeautifulSoup

async def main():
    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
        r = await client.get("https://phongtro123.com/tinh-thanh/ho-chi-minh")
        soup = BeautifulSoup(r.text, 'html.parser')
        ul = soup.find(class_="post__listing")
        if ul:
            item = ul.find("li")
            loc = item.find(class_="post-location") or item.find(class_="location") or item.find(class_="post-address")
            print("loc_class:", loc)
            loc_links = [a for a in item.find_all("a") if "tinh-thanh" in a.get("href", "") or "quan-" in a.get("href", "")]
            print("loc_links:", [(a.get("href"), a.text) for a in loc_links])
        else:
            print("No post__listing found")

asyncio.run(main())
