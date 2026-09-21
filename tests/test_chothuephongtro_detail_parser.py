import unittest
from roombeacon_crawler.sources.common_html import parse_html
from roombeacon_crawler.sources.chothuephongtro.parsers.detail_parser import ChothuephongtroDetailParser

class TestChothuephongtroDetailParser(unittest.TestCase):
    def test_extract_semantic_address(self):
        html = """
        <html>
            <body>
                <div class="section">
                    <div class="section-header"><h2>Vị trí phòng trọ</h2></div>
                    <div class="section-content">
                        Nhà Trọ An Bình hẻm 666 Nguyễn Văn Quá
                    </div>
                </div>
                <footer>
                    <div class="post-address">Footer Office Address</div>
                </footer>
            </body>
        </html>
        """
        parser = ChothuephongtroDetailParser("chothuephongtro")
        soup = parse_html(html)
        address = parser._extract_address(soup)
        self.assertEqual(address, "Nhà Trọ An Bình hẻm 666 Nguyễn Văn Quá")

    def test_ignores_other_headers(self):
        html = """
        <html>
            <body>
                <div class="section">
                    <div class="section-header"><h2>Thông tin khác</h2></div>
                    <div class="section-content">
                        Không lấy nội dung này
                    </div>
                </div>
                <div class="post-address">Địa chỉ đúng ở đây</div>
            </body>
        </html>
        """
        parser = ChothuephongtroDetailParser("chothuephongtro")
        soup = parse_html(html)
        address = parser._extract_address(soup)
        self.assertEqual(address, "Địa chỉ đúng ở đây")

if __name__ == '__main__':
    unittest.main()
