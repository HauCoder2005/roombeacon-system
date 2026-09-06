import sys
import logging
from pprint import pprint

# Cấu hình path
sys.path.append("/home/codeser/Data/projects/roombeacon/crawler/src")

from roombeacon_crawler.sources.phongtro123.parsers.detail_parser import Phongtro123DetailParser
from roombeacon_crawler.sources.chothuephongtro.parsers.detail_parser import ChothuephongtroDetailParser
from roombeacon_crawler.sources.nhatot.parsers.detail_parser import NhaTotDetailParser
from roombeacon_crawler.sources.chothuenha.parsers.detail_parser import ChothuenhaDetailParser
from roombeacon_crawler.sources.cafeland.parsers.detail_parser import CafelandDetailParser
from roombeacon_crawler.sources.tromoi.parsers.detail_parser import TromoiDetailParser
from roombeacon_crawler.sources.mogi.parsers.detail_parser import MogiDetailParser
from roombeacon_crawler.sources.nhatrovn.parsers.detail_parser import NhatrovnDetailParser

import requests

urls = {
    "phongtro123": "https://phongtro123.com/ky-tuc-xa-q1-cach-cao-dang-cao-thang-500m-tron-goi-1tr4-pr712293.html",
    "chothuephongtro": "https://chothuephongtro.me/cho-nu-thue-phong-tro-2-4a-nguyen-thi-minh-khai-phuong-da-kao-trung-tam-quan-1-pr168948.html",
    "nhatot": "https://www.nhatot.com/thue-phong-tro-thanh-pho-thu-duc-tp-ho-chi-minh/134026176.htm",
    "chothuenha": "https://chothuenha.com.vn/cho-thue-nha-tro-trung-tam-quan-1-gan-cho-ben-thanh-79158",
    "cafeland": "https://nhadat.cafeland.vn/cho-thue-phong-tro-duong-22-sau-can-ho-4s-linh-dong-thu-duc-2479238.html",
    "tromoi": "https://tromoi.com/phong-tro/nha-tro-170-32-ben-van-don-phuong-7-quan-4",
    "mogi": "https://mogi.vn/quan-8/thue-phong-tro-loi-di-rieng/cho-thue-phong-noi-that-moi-dep-3-trieu-id22747381",
    "nhatrovn": "https://nhatrovn.vn/cho-thue-phong-tro/da-nang/quan-lien-chieu/chi-tiet/6a96f797d2bb9976e7428ac0/"
}

parsers = {
    "phongtro123": Phongtro123DetailParser(),
    "chothuephongtro": ChothuephongtroDetailParser(),
    "nhatot": NhaTotDetailParser(),
    "chothuenha": ChothuenhaDetailParser(),
    "cafeland": CafelandDetailParser(),
    "tromoi": TromoiDetailParser(),
    "mogi": MogiDetailParser(),
    "nhatrovn": NhatrovnDetailParser(),
}

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}

for name, url in urls.items():
    print(f"\n--- Testing {name} ---")
    try:
        r = requests.get(url, headers=headers, timeout=10)
        html = r.text
        res = parsers[name].parse(html=html, detail_url=url, source_url=url)
        if res:
            print(f"Address: {res.address_raw[:50] if res.address_raw else None}")
            print(f"Description: {res.description_raw[:50] if res.description_raw else None}")
        else:
            print("Parser returned None")
    except Exception as e:
        print(f"Failed to fetch or parse: {e}")
