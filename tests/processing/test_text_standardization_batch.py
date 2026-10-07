import pandas as pd

import roombeacon_processing.text_standardization as text_module


def test_batch_standardization_matches_column_api_and_deduplicates_work(monkeypatch):
    source = pd.DataFrame(
        {
            "title": ["🏠 Phòng đẹp", "🏠 Phòng đẹp", None],
            "address": ["📍 Phường 7", "🏠 Phòng đẹp", None],
        }
    )
    expected = text_module.apply_text_standardization(source, "title", "title_clean")
    expected = text_module.apply_text_standardization(
        expected, "address", "address_clean"
    )
    original = text_module.standardize_text
    seen = []

    def counting_standardizer(value):
        seen.append(value)
        return original(value)

    monkeypatch.setattr(text_module, "standardize_text", counting_standardizer)
    actual = text_module.apply_text_standardization_batch(
        source,
        {"title": "title_clean", "address": "address_clean"},
    )

    pd.testing.assert_frame_equal(actual, expected)
    assert seen == ["🏠 Phòng đẹp", "📍 Phường 7"]
