"""Shared matplotlib style and chart helpers for the canonical notebooks.

Charts render as static PNGs so they stay visible on GitHub. Colors follow a
validated categorical order (identity), one blue ramp (magnitude) and a
reserved status palette (good/warning/critical); text never wears a series color.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd
from cycler import cycler

CATEGORICAL = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948")
ORDINAL_BLUES = ("#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95")
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
NEUTRAL = "#b4b2ab"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"


def apply_style() -> None:
    """Thin marks, hairline grid, no top/right spines, fixed categorical order."""
    plt.rcParams.update({
        "figure.figsize": (9, 4.2),
        "figure.dpi": 110,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": GRID,
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.grid.axis": "x",
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.labelcolor": TEXT_SECONDARY,
        "axes.labelsize": 10,
        "xtick.color": TEXT_SECONDARY,
        "ytick.color": TEXT_SECONDARY,
        "text.color": TEXT_PRIMARY,
        "legend.frameon": False,
        "axes.prop_cycle": cycler(color=list(CATEGORICAL)),
        "lines.linewidth": 2,
    })


def compact_number(value: float, _position=None) -> str:
    """Axis tick label: 1,250 -> 1.3k, 2,400,000 -> 2.4M."""
    magnitude = abs(value)
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if magnitude >= limit:
            return f"{value / limit:.3g}{suffix}"
    return f"{value:.3g}"


def _axes(ax, rows: int):
    if ax is None:
        _, ax = plt.subplots(figsize=(9, max(2.2, 0.38 * rows + 1.2)))
    return ax


def _label_bars(ax, bars, labels) -> None:
    for patch, label in zip(bars, labels):
        ax.annotate(label, (patch.get_width(), patch.get_y() + patch.get_height() / 2),
                    xytext=(4, 0), textcoords="offset points", va="center", fontsize=9, color=TEXT_SECONDARY)


def bar_chart(values: pd.Series, *, title: str, xlabel: str = "Rows", color: str | None = None,
              sort: bool = True, ax=None, fmt: str = "{:,.0f}"):
    """Horizontal bars for one measure across nominal categories (one color)."""
    data = values.sort_values(ascending=False) if sort else values
    ax = _axes(ax, len(data))
    labels = [str(i) for i in data.index]
    bars = ax.barh(labels, data.to_numpy(), color=color or CATEGORICAL[0], height=0.62)
    ax.invert_yaxis()
    _label_bars(ax, bars, [fmt.format(v) for v in data.to_numpy()])
    ax.xaxis.set_major_formatter(FuncFormatter(compact_number))
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.margins(x=0.12)
    return ax


def funnel_chart(stages: pd.Series, *, title: str, xlabel: str = "Rows", ax=None):
    """Ordered stages as an ordinal ramp, labelled with count and share of stage one."""
    ax = _axes(ax, len(stages))
    ramp = ORDINAL_BLUES[-len(stages):] if len(stages) <= len(ORDINAL_BLUES) else ORDINAL_BLUES
    colors = [ramp[min(i, len(ramp) - 1)] for i in range(len(stages))][::-1]
    bars = ax.barh([str(i) for i in stages.index], stages.to_numpy(), color=colors, height=0.62)
    ax.invert_yaxis()
    first = stages.iloc[0] or 1
    _label_bars(ax, bars, [f"{v:,.0f} ({v / first:.0%})" for v in stages.to_numpy()])
    ax.xaxis.set_major_formatter(FuncFormatter(compact_number))
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.margins(x=0.18)
    return ax


def histogram(values: pd.Series, *, title: str, xlabel: str, bins: int = 50,
              clip_quantile: float | None = 0.99, ax=None):
    """Distribution with the median marked; the long tail is clipped and stated."""
    data = pd.to_numeric(values, errors="coerce").dropna()
    if ax is None:
        _, ax = plt.subplots(figsize=(9, 3.6))
    shown = data
    if clip_quantile is not None and len(data):
        upper = data.quantile(clip_quantile)
        shown = data[data <= upper]
        xlabel = f"{xlabel}  ·  axis cut at p{clip_quantile * 100:.0f}, {len(data) - len(shown):,} higher rows not shown"
    ax.hist(shown, bins=bins, color=CATEGORICAL[0], edgecolor="white", linewidth=0.5)
    median = float(data.median()) if len(data) else np.nan
    ax.axvline(median, color=TEXT_PRIMARY, linewidth=1.2, label=f"median = {median:,.0f}")
    ax.legend(loc="upper right")
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Rows")
    ax.xaxis.set_major_formatter(FuncFormatter(compact_number))
    ax.yaxis.set_major_formatter(FuncFormatter(compact_number))
    ax.grid(axis="y")
    ax.grid(axis="x", visible=False)
    return ax


def share_chart(table: pd.DataFrame, *, title: str, colors: dict | None = None, ax=None):
    """100% stacked horizontal bars: rows are entities, columns are parts."""
    shares = table.div(table.sum(axis=1).replace(0, np.nan), axis=0).fillna(0) * 100
    ax = _axes(ax, len(shares))
    left = np.zeros(len(shares))
    labels = [str(i) for i in shares.index]
    for position, column in enumerate(shares.columns):
        color = (colors or {}).get(column, CATEGORICAL[position % len(CATEGORICAL)])
        ax.barh(labels, shares[column].to_numpy(), left=left, color=color, height=0.62,
                edgecolor="white", linewidth=2, label=str(column))
        if position == 0:
            for y, width in enumerate(shares[column].to_numpy()):
                if width >= 8:
                    ax.text(width - 1, y, f"{width:.0f}%", ha="right", va="center", fontsize=9, color="white")
        left += shares[column].to_numpy()
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("Share of rows (%)")
    ax.set_title(title)
    ax.legend(ncol=min(4, len(shares.columns)), loc="upper left", bbox_to_anchor=(0, -0.18))
    return ax
