import pytest
from roombeacon_crawler.sources.chothuenha.parsers.detail_parser import ChothuenhaDetailParser
from roombeacon_crawler.models.listing_detail_raw import ListingDetailRaw

def test_chothuenha_map_embed():
    html = """
    <html>
      <body>
        <iframe src="https://www.google.com/maps/embed/v1/place?key=AIzaSyAYDCDJAm0wsfczBkSYU66we1D_PdB9eF4&q=132 Đường Nguyễn Hữu Cảnh, Phường 22, Quận Bình Thạnh, Hồ Chí Minh&zoom=14"></iframe>
      </body>
    </html>
    """
    parser = ChothuenhaDetailParser("chothuenha")
    detail = parser.parse(html, detail_url="https://chothuenha.com.vn/cho-thue-12345.html")
    
    assert detail is not None
    assert detail.map_location is not None
    assert detail.map_location.provider == "google_maps_embed"
    assert detail.map_location.query_raw == "132 Đường Nguyễn Hữu Cảnh, Phường 22, Quận Bình Thạnh, Hồ Chí Minh"

