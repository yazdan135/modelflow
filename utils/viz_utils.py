"""
Visualization utilities for AutoML Studio.
Every function returns a Plotly Figure object styled for modern dark SaaS themes,
ready for JSON serialization via fig.to_json().
"""
import numpy as np
import pandas as pd
import plotly.graph_objs as go
import plotly.express as px


# Core SaaS Color Palette
COLORS = {
    "primary": "#6366F1",      # Indigo accent
    "secondary": "#06B6D4",    # Cyan accent
    "success": "#10B981",      # Emerald
    "warning": "#F59E0B",      # Amber
    "danger": "#EF4444",       # Rose
    "purple": "#8B5CF6",       # Violet
    "pink": "#EC4899",         # Pink
    "grid": "rgba(255, 255, 255, 0.08)",
    "text": "#F3F4F6",
    "text_muted": "#9CA3AF",
    "bg_transparent": "rgba(0,0,0,0)",
    "sequence": ["#6366F1", "#06B6D4", "#10B981", "#8B5CF6", "#F59E0B", "#EC4899", "#3B82F6"]
}


def _empty_fig(msg="No visual data available"):
    fig = go.Figure()
    fig.add_annotation(
        text=msg,
        showarrow=False,
        font=dict(size=13, color=COLORS["text_muted"], family="Inter, sans-serif"),
        xref="paper", yref="paper",
        x=0.5, y=0.5
    )
    fig.update_layout(
        paper_bgcolor=COLORS["bg_transparent"],
        plot_bgcolor=COLORS["bg_transparent"],
        margin=dict(l=20, r=20, t=30, b=20),
        height=380,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False)
    )
    return fig


def _apply_saas_theme(fig, title=None, dark_mode=True):
    fig.update_layout(
        title=dict(
            text=title or "",
font=dict(family="Inter, sans-serif", size=14, color=COLORS["text"]),            x=0.02, y=0.96
        ),
        template="plotly_dark" if dark_mode else "plotly_white",
        margin=dict(l=45, r=30, t=50, b=45),
        height=440,
        paper_bgcolor=COLORS["bg_transparent"],
        plot_bgcolor=COLORS["bg_transparent"],
        font=dict(family="Inter, system-ui, sans-serif", size=11, color=COLORS["text_muted"]),
        colorway=COLORS["sequence"],
        hoverlabel=dict(
            bgcolor="#1E293B",
            font_size=12,
            font_family="Inter, sans-serif",
            bordercolor="rgba(255,255,255,0.1)"
        )
    )
    fig.update_xaxes(
        showgrid=True, gridcolor=COLORS["grid"],
        linecolor=COLORS["grid"], zeroline=False,
        tickfont=dict(color=COLORS["text_muted"])
    )
    fig.update_yaxes(
        showgrid=True, gridcolor=COLORS["grid"],
        linecolor=COLORS["grid"], zeroline=False,
        tickfont=dict(color=COLORS["text_muted"])
    )
    return fig


def histogram(df, column, dark_mode=True):
    if column not in df.columns or df[column].dropna().empty:
        return _empty_fig(f"No numeric data in column '{column}'")
    s = df[column].dropna()
    if len(s) > 10000:
        s = s.sample(n=10000, random_state=42)
    fig = px.histogram(
        s, x=column, nbins=30,
        color_discrete_sequence=[COLORS["primary"]],
        opacity=0.85
    )
    fig.update_traces(marker_line_width=1, marker_line_color="rgba(255,255,255,0.2)")
    return _apply_saas_theme(fig, f"Histogram — {column}", dark_mode=dark_mode)


def bar_chart(df, column, top_n=15, dark_mode=True):
    if column not in df.columns or df[column].dropna().empty:
        return _empty_fig(f"No data in column '{column}'")
    counts = df[column].value_counts().head(top_n)
    fig = px.bar(
        x=counts.index.astype(str), y=counts.values,
        labels={"x": column, "y": "Count"},
        color=counts.values,
        color_continuous_scale="Viridis"
    )
    fig.update_layout(coloraxis_showscale=False)
    return _apply_saas_theme(fig, f"Frequency Distribution — {column}", dark_mode=dark_mode)


def box_plot(df, column, by=None, dark_mode=True):
    if column not in df.columns:
        return _empty_fig(f"Column '{column}' not found")
    sub_cols = [column] + ([by] if by and by in df.columns else [])
    sub_df = df[sub_cols].dropna()
    if len(sub_df) > 5000:
        sub_df = sub_df.sample(n=5000, random_state=42)
    if by and by in df.columns:
        fig = px.box(sub_df, x=by, y=column, color=by, color_discrete_sequence=COLORS["sequence"])
    else:
        fig = px.box(sub_df, y=column, color_discrete_sequence=[COLORS["secondary"]])
    return _apply_saas_theme(fig, f"Box Plot — {column}", dark_mode=dark_mode)


def violin_plot(df, column, by=None, dark_mode=True):
    if column not in df.columns:
        return _empty_fig(f"Column '{column}' not found")
    sub_cols = [column] + ([by] if by and by in df.columns else [])
    sub_df = df[sub_cols].dropna()
    if len(sub_df) > 5000:
        sub_df = sub_df.sample(n=5000, random_state=42)
    if by and by in df.columns:
        fig = px.violin(sub_df, x=by, y=column, color=by, box=True, points="outliers", color_discrete_sequence=COLORS["sequence"])
    else:
        fig = px.violin(sub_df, y=column, box=True, points="outliers", color_discrete_sequence=[COLORS["purple"]])
    return _apply_saas_theme(fig, f"Violin Plot — {column}", dark_mode=dark_mode)


def correlation_heatmap(df, numeric_cols, dark_mode=True):
    numeric_cols = [c for c in numeric_cols if c in df.columns]
    if len(numeric_cols) < 2:
        return _empty_fig("Requires at least 2 numeric columns for correlation")
    if len(numeric_cols) > 20:
        # Pick top 20 numeric columns by variance to prevent massive lag
        variances = df[numeric_cols].var(numeric_only=True).sort_values(ascending=False)
        numeric_cols = list(variances.head(20).index)
    corr = df[numeric_cols].corr(numeric_only=True).round(2)
    fig = px.imshow(
        corr, text_auto=True,
        color_continuous_scale="RdBu_r",
        zmin=-1, zmax=1,
        aspect="auto"
    )
    return _apply_saas_theme(fig, "Feature Correlation Heatmap", dark_mode=dark_mode)


def missing_bar(df, dark_mode=True):
    missing = df.isna().sum()
    missing = missing[missing > 0].sort_values(ascending=False)
    if missing.empty:
        return _empty_fig("Dataset has zero missing values 🎉")
    fig = px.bar(
        x=missing.index.astype(str), y=missing.values,
        labels={"x": "Column", "y": "Missing Cell Count"},
        color=missing.values,
        color_continuous_scale="Reds"
    )
    fig.update_layout(coloraxis_showscale=False)
    return _apply_saas_theme(fig, "Missing Values per Column", dark_mode=dark_mode)


def scatter_plot(df, x, y, color=None, dark_mode=True):
    if x not in df.columns or y not in df.columns:
        return _empty_fig("Select valid columns for scatter plot")
    sub_cols = [x, y] + ([color] if color and color in df.columns else [])
    sub_df = df[sub_cols].dropna()
    if len(sub_df) > 3000:
        sub_df = sub_df.sample(n=3000, random_state=42)
    color_col = color if color and color in df.columns else None
    fig = px.scatter(
        sub_df, x=x, y=y, color=color_col,
        opacity=0.75,
        color_discrete_sequence=COLORS["sequence"]
    )
    return _apply_saas_theme(fig, f"Scatter Plot — {x} vs {y}", dark_mode=dark_mode)


def pie_chart(df, column, top_n=8, dark_mode=True):
    if column not in df.columns or df[column].dropna().empty:
        return _empty_fig(f"No data in column '{column}'")
    counts = df[column].value_counts().head(top_n)
    fig = px.pie(
        values=counts.values, names=counts.index.astype(str),
        hole=0.4,
        color_discrete_sequence=COLORS["sequence"]
    )
    fig.update_traces(textposition='inside', textinfo='percent+label')
    return _apply_saas_theme(fig, f"Proportion Breakdown — {column}", dark_mode=dark_mode)


def target_distribution(df, target, dark_mode=True):
    if target not in df.columns:
        return _empty_fig("Target column not set")
    if pd.api.types.is_numeric_dtype(df[target]) and df[target].nunique() > 20:
        fig = px.histogram(df, x=target, marginal="box", color_discrete_sequence=[COLORS["success"]])
    else:
        counts = df[target].value_counts()
        fig = px.bar(x=counts.index.astype(str), y=counts.values, labels={"x": target, "y": "Count"}, color=counts.index.astype(str))
    return _apply_saas_theme(fig, f"Target Variable Distribution ('{target}')", dark_mode=dark_mode)


def leaderboard_bar(lb_df, metric="Accuracy", dark_mode=True):
    if lb_df is None or lb_df.empty or metric not in lb_df.columns:
        return _empty_fig("No model evaluation metrics available")
    fig = px.bar(
        lb_df, x="Model", y=metric,
        color="Model",
        text=metric,
        color_discrete_sequence=COLORS["sequence"]
    )
    fig.update_traces(texttemplate='%{text:.4f}', textposition='outside')
    fig.update_layout(showlegend=False)
    return _apply_saas_theme(fig, f"Model Leaderboard Comparison ({metric})", dark_mode=dark_mode)


def confusion_matrix_fig(cm, labels=None, dark_mode=True):
    cm = np.array(cm)
    if cm.ndim != 2 or cm.shape[0] != cm.shape[1]:
        return _empty_fig("Invalid confusion matrix dimensions")
    if not labels or len(labels) != cm.shape[0]:
        labels = [str(i) for i in range(cm.shape[0])]
    fig = px.imshow(
        cm, text_auto=True, x=labels, y=labels,
        color_continuous_scale="Blues",
        labels=dict(x="Predicted Class", y="Actual Class", color="Count")
    )
    return _apply_saas_theme(fig, "Confusion Matrix", dark_mode=dark_mode)


def roc_curve_fig(fpr, tpr, auc=None, dark_mode=True):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=fpr, y=tpr, mode="lines", name=f"ROC (AUC={round(auc,3)})" if auc else "ROC",
        line=dict(width=3, color=COLORS["primary"])
    ))
    fig.add_trace(go.Scatter(
        x=[0, 1], y=[0, 1], mode="lines", name="Random Baseline",
        line=dict(dash="dash", color=COLORS["text_muted"], width=1.5)
    ))
    fig.update_xaxes(title="False Positive Rate")
    fig.update_yaxes(title="True Positive Rate")
    title = f"Receiver Operating Characteristic (AUC={round(auc,3)})" if auc else "ROC Curve"
    return _apply_saas_theme(fig, title, dark_mode=dark_mode)


def pr_curve_fig(precision, recall, dark_mode=True):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=recall, y=precision, mode="lines", name="Precision-Recall",
        line=dict(width=3, color=COLORS["secondary"])
    ))
    fig.update_xaxes(title="Recall")
    fig.update_yaxes(title="Precision")
    return _apply_saas_theme(fig, "Precision-Recall Curve", dark_mode=dark_mode)


def feature_importance_fig(pairs, dark_mode=True):
    if not pairs:
        return _empty_fig("Feature importance not available for this model type")
    names = [p[0] for p in pairs][:15][::-1]
    values = [float(p[1]) for p in pairs][:15][::-1]
    fig = go.Figure(go.Bar(
        x=values, y=names, orientation="h",
        marker=dict(
            color=values,
            colorscale="Viridis"
        )
    ))
    fig.update_layout(showlegend=False)
    return _apply_saas_theme(fig, "Top Feature Importance", dark_mode=dark_mode)


def residual_plot(y_pred, residuals, dark_mode=True):
    fig = px.scatter(
        x=y_pred, y=residuals,
        labels={"x": "Predicted Value", "y": "Residual Error"},
        color_discrete_sequence=[COLORS["warning"]],
        opacity=0.75
    )
    fig.add_hline(y=0, line_dash="dash", line_color=COLORS["text_muted"])
    return _apply_saas_theme(fig, "Residual Analysis Plot", dark_mode=dark_mode)


def actual_vs_predicted(y_true, y_pred, dark_mode=True):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=y_true, y=y_pred, mode="markers", opacity=0.7, name="Predictions",
        marker=dict(color=COLORS["primary"], size=6)
    ))
    min_val, max_val = min(min(y_true), min(y_pred)), max(max(y_true), max(y_pred))
    fig.add_trace(go.Scatter(
        x=[min_val, max_val], y=[min_val, max_val], mode="lines", name="Ideal Match (Y=X)",
        line=dict(dash="dash", color=COLORS["success"], width=2)
    ))
    fig.update_xaxes(title="Actual Ground Truth")
    fig.update_yaxes(title="Model Predictions")
    return _apply_saas_theme(fig, "Actual vs. Predicted Plot", dark_mode=dark_mode)


def user_algorithm_pie(algo_counts, dark_mode=True):
    if not algo_counts:
        return _empty_fig("No models trained yet")
    labels = list(algo_counts.keys())
    values = list(algo_counts.values())
    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values, hole=0.45,
        textinfo="label+percent",
        marker=dict(colors=COLORS["sequence"])
    )])
    return _apply_saas_theme(fig, "Trained Models by Algorithm", dark_mode=dark_mode)


def user_task_donut(task_counts, dark_mode=True):
    if not task_counts:
        return _empty_fig("No task data available")
    labels = [k.title() for k in task_counts.keys()]
    values = list(task_counts.values())
    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values, hole=0.55,
        textinfo="label+value",
        marker=dict(colors=[COLORS["primary"], COLORS["secondary"], COLORS["purple"]])
    )])
    return _apply_saas_theme(fig, "Project Task Types", dark_mode=dark_mode)


def user_score_history_line(history_records, dark_mode=True):
    if not history_records:
        return _empty_fig("No model score history logged yet")
    df_h = pd.DataFrame(history_records)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_h["date"], y=df_h["score"],
        mode="lines+markers",
        name="Model Score",
        text=df_h["model_info"],
        hovertemplate="<b>%{text}</b><br>Score: %{y:.3f}<br>Date: %{x}<extra></extra>",
        line=dict(color=COLORS["secondary"], width=3),
        marker=dict(size=8, color=COLORS["primary"], line=dict(width=2, color="#ffffff"))
    ))
    fig.update_xaxes(title="Training Session Date/Time")
    fig.update_yaxes(title="Score Metric")
    return _apply_saas_theme(fig, "Model Score Progression Timeline", dark_mode=dark_mode)


def user_score_range_bar(min_val, avg_val, max_val, dark_mode=True):
    categories = ["Min Score", "Avg Score", "Max Score"]
    values = [round(min_val, 3), round(avg_val, 3), round(max_val, 3)]
    colors_list = [COLORS["danger"], COLORS["warning"], COLORS["success"]]
    fig = go.Figure(data=[go.Bar(
        x=categories, y=values,
        marker_color=colors_list,
        text=[f"{v:.3f}" for v in values],
        textposition="outside"
    )])
    fig.update_yaxes(range=[0, max(1.0, max_val * 1.15)])
    return _apply_saas_theme(fig, "Model Performance Score Range Summary", dark_mode=dark_mode)

