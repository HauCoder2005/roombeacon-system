import pytest
from roombeacon_crawler.sources.chothuenha.parsers.detail_parser import ChothuenhaDetailParser
from roombeacon_crawler.models.listing_detail_raw import ListingDetailRaw

def test_chothuenha_jsonld():
    html = """
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "House",
          "name": "CHO THUÊ PHÒNG TRỌ",
          "address": {
            "@type": "PostalAddress",
            "streetAddress": "132/115 Nguyễn Hữu Cảnh",
            "addressLocality": "Phường Thạnh Mỹ Tây, Bình Thạnh",
            "addressRegion": "Hồ Chí Minh"
          }
        }
        </script>
      </head>
      <body></body>
    </html>
    """
    parser = ChothuenhaDetailParser("chothuenha")
    detail = parser.parse(html, detail_url="https://chothuenha.com.vn/cho-thue-12345.html")
    
    assert detail is not None
    assert detail.address_raw is not None
    assert "132/115 Nguyễn Hữu Cảnh" in detail.address_raw

