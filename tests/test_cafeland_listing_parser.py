from roombeacon_crawler.sources.cafeland.parsers.listing_parser import CafelandListingParser

def test_cafeland_listing_parser_price_area():
    html = """
    <div class="row-item">
        <a href="/some-link-1234.html" title="Test Listing">Test Listing</a>
        <div class="reales-price">2,7 triệu /tháng</div>
        <div class="reales-area">30 m2</div>
    </div>
    """
    parser = CafelandListingParser("cafeland")
    records = parser.parse(html, "https://nhadat.cafeland.vn/", 1, 50)
    assert len(records) == 1
    res = records[0]
    assert res.price_raw == "2,7 triệu /tháng"
    assert res.area_raw == "30 m2"
