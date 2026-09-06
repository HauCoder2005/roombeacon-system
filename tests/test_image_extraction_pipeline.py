import pytest
from roombeacon_crawler.sources.common_html import (
    extract_best_image_url,
    extract_scoped_images,
    parse_html,
    SourceDetailParser
)
from roombeacon_crawler.models.listing_detail_raw import ListingDetailRaw

def test_extract_best_image_url():
    # Test data-original priority
    html = '<img src="thumb.jpg" data-original="highres.jpg">'
    root = parse_html(html)
    img = root.first(tag="img")
    assert extract_best_image_url(img.attrs, "https://example.com") == "https://example.com/highres.jpg"
    
    # Test srcset priority
    html = '<img src="thumb.jpg" srcset="small.jpg 300w, large.jpg 1000w, medium.jpg 500w">'
    root = parse_html(html)
    img = root.first(tag="img")
    assert extract_best_image_url(img.attrs, "https://example.com") == "https://example.com/large.jpg"
    
    # Test fallback to src
    html = '<img src="thumb.jpg">'
    root = parse_html(html)
    img = root.first(tag="img")
    assert extract_best_image_url(img.attrs, "https://example.com") == "https://example.com/thumb.jpg"

    # Test ignoring data:
    html = '<img src="data:image/png;base64,iVBORw0KGgo">'
    root = parse_html(html)
    img = root.first(tag="img")
    assert extract_best_image_url(img.attrs, "https://example.com") is None

def test_extract_scoped_images_ignores_outside():
    html = """
    <html>
        <header><img src="logo.png"></header>
        <div class="image-gallery">
            <img src="img1.jpg">
            <img src="img2.jpg">
        </div>
        <footer><img src="ads.jpg"></footer>
    </html>
    """
    root = parse_html(html)
    container = root.first(class_token="image-gallery")
    images = extract_scoped_images(container, "https://example.com")
    
    assert images == [
        "https://example.com/img1.jpg", 
        "https://example.com/img2.jpg"
    ]

def test_source_detail_parser_json_ld_fallback():
    class TestParser(SourceDetailParser):
        GALLERY_CLASSES = ("non-existent-gallery",)
        
    html = """
    <html>
        <script type="application/ld+json">
        {
            "@type": "Product",
            "image": ["https://cdn.com/1.jpg", "https://cdn.com/2.jpg"]
        }
        </script>
        <img src="logo.jpg">
    </html>
    """
    parser = TestParser("test")
    detail = parser.parse(html, "https://example.com")
    
    # logo.jpg must be ignored, JSON-LD images must be extracted
    assert detail.image_urls_raw == ["https://cdn.com/1.jpg", "https://cdn.com/2.jpg"]

def test_source_detail_parser_json_ld_organization_ignored():
    class TestParser(SourceDetailParser):
        GALLERY_CLASSES = ("non-existent-gallery",)
        
    html = """
    <html>
        <script type="application/ld+json">
        {
            "@type": "Organization",
            "image": "https://cdn.com/logo.jpg"
        }
        </script>
        <img src="logo.jpg">
    </html>
    """
    parser = TestParser("test")
    detail = parser.parse(html, "https://example.com")
    
    # logo.jpg must be ignored, JSON-LD organization image must be ignored
    assert detail.image_urls_raw == []

def test_source_detail_parser_empty_fallback():
    class TestParser(SourceDetailParser):
        GALLERY_CLASSES = ("non-existent-gallery",)
        
    html = """
    <html>
        <img src="logo.jpg">
    </html>
    """
    parser = TestParser("test")
    detail = parser.parse(html, "https://example.com")
    
    # Should fall back to empty list because there is no JSON-LD and no gallery
    assert detail.image_urls_raw == []
