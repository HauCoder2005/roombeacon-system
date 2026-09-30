import urllib.request
from bs4 import BeautifulSoup
import sys
url = 'https://phongtro123.com/tinh-thanh/ho-chi-minh'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
html = urllib.request.urlopen(req).read().decode('utf-8')
soup = BeautifulSoup(html, 'html.parser')
ul = soup.find(class_="post__listing")
if ul:
    item = ul.find("li")
    print(item.prettify())
