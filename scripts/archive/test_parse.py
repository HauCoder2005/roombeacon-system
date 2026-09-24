from roombeacon_crawler.sources.phongtro123.parsers.listing_parser import DOMTreeBuilder
import urllib.request

html = """
<li class="bg-white shadow-sm rounded p-3 mt-3">
    <a href="/tinh-thanh/ho-chi-minh/quan-7">Quận 7, Hồ Chí Minh</a>
</li>
"""
builder = DOMTreeBuilder()
builder.feed(html)
li = builder.root.find_all(tag="li")[0]
links = li.find_all(tag="a")
print("Links count:", len(links))
for a in links:
    print("href:", a.attrs.get("href"))
    print("text:", a.get_text())

