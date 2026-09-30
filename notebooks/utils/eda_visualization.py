"""Small reusable plotting helpers; all inputs must be runtime aggregates."""

import pandas as pd
import plotly.express as px
from IPython.display import Markdown, display


def counts(series, category='category'):
    """Count all rows of series, including nulls; return category/count/rate table."""
    table = series.fillna('(missing)').value_counts(dropna=False).rename_axis(category).reset_index(name='count')
    table['percent'] = table['count'] / max(len(series), 1) * 100
    return table


def bar(
    table, category, value, title, color=None, *, orientation=None, text=None,
    order=None, labels=None, barmode=None,
):
    """Plot a simple aggregate bar chart and return the displayed figure.

    Six or more categories default to horizontal bars. Callers can preserve a
    meaningful sequence (for example validation stages) with ``order``.
    """
    orientation = orientation or ('h' if table[category].nunique() >= 6 else 'v')
    axis_labels = {
        value: value.replace('_', ' '), category: category.replace('_', ' '),
    }
    axis_labels.update(labels or {})
    x, y = (value, category) if orientation == 'h' else (category, value)
    figure = px.bar(
        table, x=x, y=y, color=color, orientation=orientation, text=text,
        title=title, template='plotly_white', labels=axis_labels,
        hover_data=[c for c in ['count', 'percent'] if c in table and c != value],
        category_orders={category: order} if order else None,
        barmode=barmode,
    )
    if not order:
        axis = figure.layout.yaxis if orientation == 'h' else figure.layout.xaxis
        axis.categoryorder = 'total ascending' if orientation == 'h' else 'total descending'
    figure.update_traces(textposition='auto')
    figure.update_layout(
        height=max(360, 25 * table[category].nunique() + 150) if orientation == 'h' else 430,
        margin={'l': 30, 'r': 30, 't': 90, 'b': 70},
    )
    figure.show()
    return figure


def heatmap(
    table, title, percent=False, annotation_text=None, x_title=None, y_title=None,
    show_colorbar=True,
):
    """Plot a numeric matrix table; return figure, with percent bounds when requested."""
    show_numbers = percent and table.size <= 120 and annotation_text is None
    figure = px.imshow(table, aspect='auto', title=title, template='plotly_white',
                        color_continuous_scale='Blues',
                        zmin=0 if percent else None, zmax=100 if percent else None,
                        text_auto='.1f' if show_numbers else annotation_text is not None,
                        labels={'color': 'Tỷ lệ (%)' if percent else 'Giá trị'})
    if annotation_text is not None:
        figure.update_traces(text=annotation_text, texttemplate='%{text}')
    figure.update_coloraxes(showscale=show_colorbar)
    figure.update_layout(
        height=max(380, 28 * len(table) + 180),
        margin={'l': 30, 'r': 30, 't': 80, 'b': 100},
        xaxis_title=x_title, yaxis_title=y_title,
    )
    figure.show()
    return figure


def finding(observation, conclusion):
    """Render runtime observation and restrained conclusion strings; return None."""
    display(Markdown(f'### Quan sát\n{observation}\n\n### Kết luận\n{conclusion}'))
