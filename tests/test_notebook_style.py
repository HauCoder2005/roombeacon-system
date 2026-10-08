import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from notebooks.utils import notebook_style as style


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def test_apply_style_sets_recessive_chrome():
    style.apply_style()

    assert plt.rcParams["axes.spines.top"] is False
    assert plt.rcParams["axes.spines.right"] is False
    assert plt.rcParams["axes.prop_cycle"].by_key()["color"][:2] == list(style.CATEGORICAL[:2])


def test_bar_chart_uses_one_color_and_sorts_largest_first():
    ax = style.bar_chart(pd.Series({"a": 1, "b": 5, "c": 3}), title="Counts", xlabel="Rows")

    labels = [tick.get_text() for tick in ax.get_yticklabels()]
    assert labels == ["b", "c", "a"]
    assert {patch.get_facecolor() for patch in ax.patches} == {matplotlib.colors.to_rgba(style.CATEGORICAL[0])}
    assert ax.get_title(loc="left") == "Counts"


def test_funnel_chart_keeps_stage_order_and_labels_share_of_first_stage():
    stages = pd.Series({"All": 200, "Valid": 150, "Eligible": 50})

    ax = style.funnel_chart(stages, title="Funnel")

    assert [tick.get_text() for tick in ax.get_yticklabels()] == ["All", "Valid", "Eligible"]
    assert [text.get_text() for text in ax.texts] == ["200 (100%)", "150 (75%)", "50 (25%)"]


def test_histogram_marks_the_median():
    ax = style.histogram(pd.Series([1.0, 2.0, 3.0, 4.0, 100.0]), title="Dist", xlabel="Value", clip_quantile=None)

    assert any("median" in (line.get_label() or "") for line in ax.get_lines())


def test_share_chart_stacks_each_row_to_one_hundred_percent():
    table = pd.DataFrame({"ok": [3, 1], "bad": [1, 1]}, index=["x", "y"])

    ax = style.share_chart(table, title="Share")

    widths = pd.Series([patch.get_width() for patch in ax.patches])
    assert widths.round(6).tolist() == [75.0, 50.0, 25.0, 50.0]


@pytest.mark.parametrize(("value", "label"), [(950, "950"), (1250, "1.25k"), (150000, "150k"), (2_400_000, "2.4M")])
def test_compact_number_formats_axis_ticks(value, label):
    assert style.compact_number(value) == label
