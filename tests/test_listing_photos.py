"""Only a listing's own photos become assets: no page chrome, no related-listing thumbnails."""

from roombeacon_crawler.application.assets.listing_photos import is_page_chrome, select_listing_photos, select_post_photos


def _urls(selected):
    return [url for _position, url in selected]


def test_phongtro123_keeps_gallery_size_and_drops_related_cards_and_chrome():
    images = [
        (1, "/images/logo-phongtro.svg?v=2026"),
        (2, "https://pt123.cdn.static123.com/images/thumbs/900x600/fit/2026/09/18/own-1.jpg"),
        (3, "https://pt123.cdn.static123.com/images/thumbs/900x600/fit/2026/09/18/own-2.jpg"),
        (4, "https://phongtro123.com/images/default-user.svg"),
        (5, "https://pt123.cdn.static123.com/images/thumbs/450x300/fit/2026/10/10/other-listing.jpg"),
    ]

    selected = select_listing_photos("phongtro123", "tinh-thanh/ho-chi-minh/x", images)

    assert selected == [images[1], images[2]]


def test_expired_phongtro123_page_with_only_related_cards_has_no_photos():
    # A detail page always opens with the site logo; the rest are related-listing cards.
    images = [(1, "/images/logo-phongtro.svg?v=2026")]
    images += [(i, f"https://pt123.cdn.static123.com/images/thumbs/450x300/fit/2026/10/10/other-{i}.jpg") for i in range(2, 28)]

    assert select_listing_photos("phongtro123", "x", images) == []


def test_chothuephongtro_keeps_only_gallery_size():
    own = "https://ctpt.cdn.static123.com/images/thumbs/900x600/fit/2026/10/10/img-0022.jpg"
    related = "https://ctpt.cdn.static123.com/images/thumbs/450x300/fit/2026/10/10/img-0005.jpg"

    assert _urls(select_listing_photos("chothuephongtro", "170174", [(1, own), (2, related)])) == [own]


def test_cafeland_mogi_nhatot_keep_their_photo_cdn_only():
    cases = {
        "cafeland": (
            "https://static2.cafeland.vn/static01/sgd/cnews/2026/9/309647300-cho-thue-1-.jpg",
            ["https://nhadat.cafeland.vn/user/assets/img/logo-new/logo-new-2024.png",
             "https://static2.cafeland.vn/member/avatar/2026/hinh3n.jpg",
             "https://static1.cafeland.vn/cafelandnew//hinh-anh/2024/06/24/211/1100-135-nhadat.jpg?v=1"],
        ),
        "mogi": (
            "https://cloud.mogi.vn/images/2026/09/27/213/1d9ddb1f06fd4413aeceac926d8a78e8.jpg",
            ["https://mogi.vn/content/images/avatar.png",
             "https://images.dmca.com/Badges/dmca_protected_sml_120m.png?ID=1",
             "https://cloud.mogi.vn/profile/thumb-mavatar/1.jpg"],
        ),
        "nhatot": (
            "https://cdn.chotot.com/R2e-oTyc9paIQ/preset:view/plain/7deeab6dc6e64c56-2996851629990697395.jpg",
            ["https://static.chotot.com/storage/empty_state/desktop/ad_not_found.png",
             "https://static.chotot.com/storage/icons/logos/ad-param/size.png"],
        ),
    }
    for source, (photo, chrome) in cases.items():
        images = [(i, url) for i, url in enumerate(chrome + [photo], start=1)]
        assert _urls(select_listing_photos(source, "1", images)) == [photo], source


def test_nhatrovn_keeps_images_of_its_own_room_only():
    own = "https://api.nhatrovn.vn/api/common/img/6a4f/images-room/6ab7a41bd954c8459a699c91/6ab7/a.jpg"
    other = "https://api.nhatrovn.vn/api/common/img/6a4f/images-room/6aaaaaaaaaaaaaaaaaaaaaaa/6ab7/b.jpg"

    assert _urls(select_listing_photos("nhatrovn", "6ab7a41bd954c8459a699c91", [(1, own), (2, other)])) == [own]


def test_tromoi_keeps_the_first_hostel_and_drops_related_hostels():
    own = [f"https://tromoi.com/storage/uploads/hosts/10107/hostels/31824/own{i}.webp" for i in range(3)]
    related = ["https://tromoi.com/storage/uploads/hosts/8/hostels/18919/rel.webp"]
    images = [(1, "https://tromoi.com/images/logo.png")] + [(i + 2, url) for i, url in enumerate(own)]
    images += [(10, "https://tromoi.com/images/icons/icon_wifi.svg"), (11, related[0])]

    assert _urls(select_listing_photos("tromoi", "phong-tro/x-34403", images)) == own


def test_chothuenha_keeps_uploaded_photos_not_site_icons():
    photo = "https://giga-images.s3.ap-southeast-1.amazonaws.com/6ac232d92964e51594d75ac0-1791255966.jpeg"
    images = [
        (1, "https://www.facebook.com/tr?id=1732242027950254&ev=PageView&noscript=1"),
        (2, "https://chothuenha.com.vn/datafiles/1746612594_logo-websitr.jpg"),
        (3, "https://chothuenha.com.vn/datafiles/1709103523_2.png"),
        (4, photo),
    ]

    assert _urls(select_listing_photos("chothuenha", "79960", images)) == [photo]


def test_unknown_source_falls_back_to_dropping_page_chrome():
    photo = "https://static.muaban.net/images/2026/10/01/abc.jpg"
    images = [(1, "https://muaban.net/images/logo.svg"), (2, "https://muaban.net/assets/icon-phone.png"), (3, photo)]

    assert _urls(select_listing_photos("muaban", "71254829", images)) == [photo]


def test_positions_are_kept_and_duplicates_dropped():
    url = "https://cloud.mogi.vn/images/2026/09/27/213/a.jpg"

    assert select_listing_photos("mogi", "1", [(4, url), (9, url)]) == [(4, url)]


def test_page_chrome_detection():
    for url in (
        "data:image/png;base64,AAAA",
        "/images/logo.svg",
        "https://x.vn/favicon.png",
        "https://www.facebook.com/tr?id=1",
        "https://x.vn/images/default_user.svg",
        "https://x.vn/content/images/icons/zl-icon.png",
    ):
        assert is_page_chrome(url), url
    assert not is_page_chrome("https://cloud.mogi.vn/images/2026/09/27/213/a.jpg")


def test_first_image_is_the_listing_card_cover_and_is_kept():
    # The loader puts the search-card thumbnail first; static123 serves it at 450x300.
    cover = "https://pt123.cdn.static123.com/images/thumbs/450x300/fit/2022/10/10/own-cover.jpg"
    gallery = "https://pt123.cdn.static123.com/images/thumbs/900x600/fit/2022/10/10/own-1.jpg"
    related = "https://pt123.cdn.static123.com/images/thumbs/450x300/fit/2026/10/10/other.jpg"
    images = [(1, cover), (2, "/images/logo-phongtro.svg"), (3, gallery), (4, related)]

    assert _urls(select_listing_photos("phongtro123", "x", images)) == [cover, gallery]


def test_first_image_that_is_page_chrome_is_still_dropped():
    images = [(1, "https://mogi.vn/content/Images/logo.svg"), (2, "https://cloud.mogi.vn/images/2026/a.jpg")]

    assert _urls(select_listing_photos("mogi", "1", images)) == ["https://cloud.mogi.vn/images/2026/a.jpg"]


def test_post_photos_are_the_union_of_every_version():
    cover = "https://pt123.cdn.static123.com/images/thumbs/450x300/fit/2022/10/10/own-cover.jpg"
    gallery = "https://pt123.cdn.static123.com/images/thumbs/900x600/fit/2022/10/10/own-1.jpg"
    card_only_version = [(1, cover)]
    detail_version = [(1, cover), (2, gallery)]

    selected = select_post_photos("phongtro123", "x", [detail_version, card_only_version])

    assert selected == [(1, cover), (2, gallery)]


def test_tromoi_gallery_ends_at_the_amenity_icons_and_includes_legacy_uploads():
    legacy = "https://tromoi.com/storage/legacy_uploads/static/phong_tro_hcm/Quan_11/153%20tran%20quy/z1.jpg"
    own = "https://tromoi.com/storage/uploads/hosts/9/hostels/28539/a.webp"
    related = "https://tromoi.com/storage/uploads/hosts/8/hostels/18919/b.webp"
    images = [
        (1, "https://tromoi.com/images/logo.png"),
        (2, legacy),
        (3, own),
        (4, "https://tromoi.com/images/icons/icon_wifi.svg"),
        (5, related),
    ]

    assert _urls(select_listing_photos("tromoi", "phong-tro/nha-tro-so-153", images)) == [legacy, own]
