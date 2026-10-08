"""Shared matplotlib style and chart helpers for the canonical notebooks.

Charts render as static PNGs so they stay visible on GitHub. Colors follow a
validated categorical order (identity), one blue ramp (magnitude) and a
reserved status palette (good/warning/critical); text never wears a series color.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MaxNLocator
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


def percent(share: float) -> str:
    """0.75 -> '75%', 0.998 -> '99.8%': one decimal only when it carries information."""
    value = round(share * 100, 1)
    return f"{value:.0f}%" if value == int(value) else f"{value:.1f}%"


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
    values = data.to_numpy(dtype=float)
    if len(values) and values.max() < 25 and np.allclose(values, np.round(values)):
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
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
    _label_bars(ax, bars, [f"{v:,.0f} ({percent(v / first)})" for v in stages.to_numpy()])
    ax.xaxis.set_major_formatter(FuncFormatter(compact_number))
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.margins(x=0.18)
    return ax


def histogram(values: pd.Series, *, title: str, xlabel: str, bins: int = 50,
              clip_quantile: float | None = 0.99, log_x: bool = False, ax=None):
    """Distribution with the median marked; the long tail is clipped and stated.

    ``log_x`` shows heavily skewed raw values on log-spaced bins (positive values only).
    """
    data = pd.to_numeric(values, errors="coerce").dropna()
    if log_x:
        data = data[data > 0]
    if ax is None:
        _, ax = plt.subplots(figsize=(9, 3.6))
    shown = data
    if clip_quantile is not None and len(data):
        upper = data.quantile(clip_quantile)
        shown = data[data <= upper]
        xlabel = f"{xlabel}  ·  axis cut at p{clip_quantile * 100:.0f}, {len(data) - len(shown):,} higher rows not shown"
    if log_x and len(shown):
        bins = np.logspace(np.log10(shown.min()), np.log10(shown.max()), bins)
        ax.set_xscale("log")
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


def status_chart(counts: pd.Series, *, tiers: dict, title: str, xlabel: str = "Rows", ax=None):
    """Status counts in their given order; color = tier (good/warning/serious/critical).

    Every bar keeps its status label and a count/percent label, so the tier
    color is never the only carrier of meaning. Untiered statuses are neutral.
    """
    ax = _axes(ax, len(counts))
    labels = [str(i) for i in counts.index]
    colors = [STATUS.get(tiers.get(label, ""), NEUTRAL) for label in labels]
    bars = ax.barh(labels, counts.to_numpy(), color=colors, height=0.62)
    ax.invert_yaxis()
    total = counts.sum() or 1
    _label_bars(ax, bars, [f"{v:,.0f} ({v / total:.1%})" for v in counts.to_numpy()])
    ax.xaxis.set_major_formatter(FuncFormatter(compact_number))
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.margins(x=0.2)
    return ax


def scatter_legend(ax) -> None:
    """Place a scatter legend below the plot so it never hides points."""
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.14), ncol=2, markerscale=2)
    for handle in ax.get_legend().legend_handles:
        handle.set_alpha(1)


def heatmap(table: pd.DataFrame, *, title: str, fmt: str = "{:.0f}", vmin: float = 0,
            vmax: float | None = None, label: str = "", ax=None):
    """Sequential one-hue (blue) matrix; every non-missing cell carries its value."""
    from matplotlib.colors import LinearSegmentedColormap

    cmap = LinearSegmentedColormap.from_list("rb_blues", ["#f4f8fd", *ORDINAL_BLUES[1:]]).with_extremes(bad="#f0efec")
    values = table.to_numpy(dtype=float)
    if ax is None:
        _, ax = plt.subplots(figsize=(max(6, 0.9 * table.shape[1] + 3), max(2.6, 0.42 * table.shape[0] + 1.4)))
    upper = vmax if vmax is not None else np.nanmax(values)
    image = ax.imshow(np.ma.masked_invalid(values), aspect="auto", cmap=cmap, vmin=vmin, vmax=upper)
    ax.set_xticks(range(table.shape[1]), [str(c) for c in table.columns], rotation=35, ha="right")
    ax.set_yticks(range(table.shape[0]), [str(i) for i in table.index])
    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for row in range(table.shape[0]):
        for col in range(table.shape[1]):
            value = values[row, col]
            if np.isfinite(value):
                dark = (value - vmin) / ((upper - vmin) or 1) > 0.55
                ax.text(col, row, fmt.format(value), ha="center", va="center", fontsize=8,
                        color="white" if dark else TEXT_PRIMARY)
    colorbar = plt.colorbar(image, ax=ax, fraction=0.03, pad=0.02)
    colorbar.outline.set_visible(False)
    colorbar.set_label(label)
    ax.set_title(title)
    return ax


def range_chart(frame: pd.DataFrame, *, low: str, mid: str, high: str, title: str, xlabel: str,
                ax=None, fmt=compact_number):
    """Median dot with a P25-P75 line per row (replaces box plots; order is kept)."""
    ax = _axes(ax, len(frame))
    positions = np.arange(len(frame))
    ax.hlines(positions, frame[low], frame[high], color=ORDINAL_BLUES[0], linewidth=4, label="P25–P75")
    ax.scatter(frame[mid], positions, color=CATEGORICAL[0], s=36, zorder=3, edgecolors="white",
               linewidths=1.5, label="median")
    for y, value in zip(positions, frame[mid]):
        ax.annotate(fmt(value), (value, y), xytext=(0, 7), textcoords="offset points", ha="center",
                    fontsize=8, color=TEXT_SECONDARY)
    ax.set_yticks(positions, [str(i) for i in frame.index])
    ax.set_ylim(len(frame) - 0.5, -0.8)  # top-down order, room for the first median label
    ax.xaxis.set_major_formatter(FuncFormatter(compact_number))
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.legend(loc="lower right", bbox_to_anchor=(1, 1), ncol=2, borderaxespad=0.2)
    return ax
