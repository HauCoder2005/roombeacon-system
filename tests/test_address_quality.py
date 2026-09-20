from roombeacon_crawler.sources.address_quality import has_street_evidence, most_specific_address
from roombeacon_crawler.sources.common_html import SourceDetailParser


def test_coarse_location_is_not_a_street():
    for value in ('An Hội Tây TP. Hồ Chí Minh', 'Phường 2, Quận 3', None):
        assert not has_street_evidence(value)


def test_number_or_explicit_street_is_preferred():
    assert most_specific_address('Phường 1, HCM', '123/4 Lê Lợi, HCM') == '123/4 Lê Lợi, HCM'
    assert has_street_evidence('Đường Nguyễn Trãi, Phường 2')


def test_coarse_jsonld_does_not_hide_labeled_street():
    html = '''<script type="application/ld+json">{"@type":"Apartment","address":{"addressLocality":"Phường 1","addressRegion":"Hồ Chí Minh"}}</script><p>Địa chỉ: 123 Lê Lợi, Phường 1</p>'''
    detail = SourceDetailParser('test').parse(html, detail_url='https://example.com/123')
    assert detail.address_raw == '123 Lê Lợi, Phường 1'
