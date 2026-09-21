import unittest
from roombeacon_crawler.sources.map_extractor import MapLocationExtractor

class TestMapLocationExtractor(unittest.TestCase):
    def test_case1_q_coordinates(self):
        url = "https://maps.google.com/maps?q=10.12345,106.54321&hl=es"
        loc = MapLocationExtractor.extract_from_url(url)
        self.assertIsNotNone(loc)
        self.assertEqual(loc.latitude, 10.12345)
        self.assertEqual(loc.longitude, 106.54321)
        self.assertIsNone(loc.query_raw)
        self.assertEqual(loc.provider, "google_maps_embed")

    def test_case2_path_coordinates(self):
        url = "https://www.google.com/maps/@10.12345,106.54321,15z"
        loc = MapLocationExtractor.extract_from_url(url)
        self.assertIsNotNone(loc)
        self.assertEqual(loc.latitude, 10.12345)
        self.assertEqual(loc.longitude, 106.54321)

    def test_case3_google_embed_encoded(self):
        url = "https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d1!2d106.54321!3d10.12345!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x0%3A0x0!2z!5e0!3m2!1svi!2s"
        loc = MapLocationExtractor.extract_from_url(url)
        self.assertIsNotNone(loc)
        self.assertEqual(loc.latitude, 10.12345)
        self.assertEqual(loc.longitude, 106.54321)

    def test_case4_text_query_only(self):
        url = "https://maps.google.com/maps?q=Phường+2,+Tân+Bình"
        loc = MapLocationExtractor.extract_from_url(url)
        self.assertIsNotNone(loc)
        self.assertIsNone(loc.latitude)
        self.assertIsNone(loc.longitude)
        self.assertEqual(loc.query_raw, "Phường 2, Tân Bình")

    def test_case5_malformed_coordinate(self):
        url = "https://maps.google.com/maps?q=10.12345,abc"
        loc = MapLocationExtractor.extract_from_url(url)
        self.assertIsNotNone(loc)
        self.assertIsNone(loc.latitude)
        self.assertEqual(loc.query_raw, "10.12345,abc")

    def test_case6_out_of_range_coordinate(self):
        url = "https://maps.google.com/maps?q=200,500"
        loc = MapLocationExtractor.extract_from_url(url)
        self.assertIsNotNone(loc)
        self.assertIsNone(loc.latitude)
        self.assertEqual(loc.query_raw, "200,500")

    def test_case7_non_map_url(self):
        url = "https://example.com/not-a-map"
        loc = MapLocationExtractor.extract_from_url(url)
        self.assertIsNone(loc)
        
    def test_case_ll_coordinates(self):
        url = "https://maps.google.com/maps?ll=10.12345,106.54321"
        loc = MapLocationExtractor.extract_from_url(url)
        self.assertIsNotNone(loc)
        self.assertEqual(loc.latitude, 10.12345)
        self.assertEqual(loc.longitude, 106.54321)

if __name__ == '__main__':
    unittest.main()


def test_lazy_embed_preserves_coordinates_and_address():
    import base64
    address = '123 Đường Lê Lợi, Phường 1'
    encoded = base64.urlsafe_b64encode(address.encode()).decode().rstrip('=')
    html = f'<IFRAME data-src="https://www.google.com/maps/embed?pb=%213d10%214d106%212z{encoded}"></IFRAME>'
    loc = MapLocationExtractor.extract_map_from_html(html)
    assert (loc.latitude, loc.longitude, loc.query_raw) == (10, 106, address)


def test_prefers_coordinates_over_first_coarse_map():
    html = '<iframe src="https://maps.google.com/maps?q=Hanoi"></iframe><iframe src="https://maps.google.com/maps?q=10,%20106"></iframe>'
    assert MapLocationExtractor.extract_map_from_html(html).latitude == 10


def test_rejects_lookalike_map_host():
    assert MapLocationExtractor.extract_from_url('https://google.com.evil.test/maps?q=10,106') is None


def test_query_literal_plus_is_not_decoded_twice():
    loc = MapLocationExtractor.extract_from_url('https://www.google.com/maps/search/?api=1&query=A%2BB')
    assert loc.query_raw == 'A+B'


def test_html_entity_query_separator():
    loc = MapLocationExtractor.extract_from_url('https://maps.google.com/maps?output=embed&amp;q=10,106')
    assert (loc.latitude, loc.longitude) == (10, 106)
