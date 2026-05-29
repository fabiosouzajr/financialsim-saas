"""Cores, tipografia, espaçamentos da UI."""

from __future__ import annotations

PRIMARY       = "#2563EB"   # blue-600 — confiança, profissional
SECONDARY     = "#3B82F6"
ACCENT        = "#F59E0B"
ERROR         = "#DC2626"
WARNING       = "#F59E0B"
SUCCESS       = "#16A34A"
BG            = "#F1F5F9"   # slate-100
SURFACE       = "#FFFFFF"
TEXT          = "#0F172A"   # slate-900
TEXT_MUTED    = "#64748B"   # slate-500
SIDEBAR_BG    = "#0F172A"   # slate-900
SIDEBAR_HOVER = "#1E293B"   # slate-800

FONT_FAMILY = "'IBM Plex Sans', 'Segoe UI', Arial, sans-serif"

SIZE_XS   = "0.75rem"
SIZE_SM   = "0.875rem"
SIZE_BASE = "1rem"
SIZE_LG   = "1.25rem"
SIZE_XL   = "1.5rem"
SIZE_2XL  = "2rem"

RADIUS = "0.75rem"


def apply_global_styles() -> None:
    """Call once at app startup to register CSS."""
    from nicegui import ui
    ui.add_head_html(f"""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>

    /* ── Base ─────────────────────────────────────────────────────── */
    * {{ box-sizing: border-box; }}
    body {{
        font-family: {FONT_FAMILY} !important;
        background: {BG};
        color: {TEXT};
        -webkit-font-smoothing: antialiased;
    }}

    /* ── Header ───────────────────────────────────────────────────── */
    .app-header {{
        background: {SURFACE} !important;
        border-bottom: 1px solid #e2e8f0 !important;
        min-height: 52px !important;
        max-height: 52px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
    }}
    .app-header .q-toolbar {{
        min-height: 52px !important;
        padding: 0 1rem;
    }}

    /* ── Sidebar ──────────────────────────────────────────────────── */
    .app-sidebar .q-drawer,
    .app-sidebar .q-drawer__content {{
        background: {SIDEBAR_BG} !important;
        border-right: none !important;
    }}
    .sidebar-divider {{
        border: none;
        border-top: 1px solid #1e293b;
        margin: 0 1rem;
    }}
    .sidebar-brand-icon {{ font-size: 1.375rem !important; }}
    .sidebar-brand-name {{ letter-spacing: -0.01em; }}

    /* ── Nav Items ────────────────────────────────────────────────── */
    .nav-item {{
        display: flex;
        align-items: center;
        gap: 0.75rem;
        padding: 0.5625rem 0.75rem;
        border-radius: 0.5rem;
        cursor: pointer;
        transition: background-color 0.14s ease, color 0.14s ease;
        user-select: none;
        width: 100%;
    }}
    .nav-item:hover {{
        background-color: {SIDEBAR_HOVER};
    }}
    .nav-icon {{
        color: #64748b;
        font-size: 1.1rem !important;
        width: 1.25rem;
        flex-shrink: 0;
        transition: color 0.14s ease;
    }}
    .nav-label {{
        color: #94a3b8;
        font-size: 0.875rem;
        font-weight: 500;
        transition: color 0.14s ease;
        white-space: nowrap;
    }}
    .nav-item:hover .nav-icon {{ color: #e2e8f0; }}
    .nav-item:hover .nav-label {{ color: #f1f5f9; }}

    /* ── Page Container ───────────────────────────────────────────── */
    .q-page-container,
    .q-page {{
        background: {BG} !important;
    }}

    /* ── KPI Cards ────────────────────────────────────────────────── */
    .kpi-card {{
        background: {SURFACE};
        border-radius: {RADIUS};
        padding: 1.25rem 1.5rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.07), 0 1px 2px rgba(0,0,0,0.04);
        border: 1px solid #e2e8f0;
        min-width: 160px;
        transition: box-shadow 150ms ease, border-color 150ms ease;
    }}
    .kpi-card:hover {{
        box-shadow: 0 4px 12px rgba(0,0,0,0.10);
        border-color: #cbd5e1;
    }}
    .kpi-value {{
        font-size: 1.875rem;
        font-weight: 700;
        color: {PRIMARY};
        letter-spacing: -0.025em;
        line-height: 1.2;
        font-variant-numeric: tabular-nums;
    }}
    .kpi-label {{
        font-size: 0.6875rem;
        color: {TEXT_MUTED};
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 0.375rem;
    }}

    /* ── Badges ───────────────────────────────────────────────────── */
    .badge-warn {{
        background: {WARNING};
        color: white;
        padding: 0.2rem 0.6rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
    }}

    /* ── Tables ───────────────────────────────────────────────────── */
    .q-table thead th {{
        font-size: 0.6875rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: {TEXT_MUTED};
        font-weight: 600;
        background: #f8fafc !important;
    }}
    .q-table tbody td {{
        color: {TEXT};
        font-size: 0.875rem;
        font-variant-numeric: tabular-nums;
    }}
    .q-table__container {{
        border-radius: {RADIUS};
        border: 1px solid #e2e8f0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        overflow: hidden;
    }}
    .q-table tbody tr:hover td {{
        background: #f8fafc !important;
    }}

    /* ── Form Inputs ──────────────────────────────────────────────── */
    .q-field--outlined .q-field__control {{
        border-radius: 0.5rem !important;
    }}
    .q-field--outlined .q-field__control:hover:before {{
        border-color: {PRIMARY} !important;
    }}
    .q-field__label {{
        font-weight: 500 !important;
        font-size: 0.875rem !important;
    }}

    /* ── Buttons ──────────────────────────────────────────────────── */
    .q-btn:not(.q-btn--flat):not(.q-btn--outline) {{
        border-radius: 0.5rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.01em !important;
    }}
    .q-btn--flat {{ border-radius: 0.375rem !important; }}
    .q-btn:active {{
        transform: scale(0.96);
        transition-duration: 80ms !important;
    }}

    /* ── Cards ────────────────────────────────────────────────────── */
    .q-card {{
        border-radius: {RADIUS} !important;
        border: 1px solid #e2e8f0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.07) !important;
    }}

    /* ── Expansion ────────────────────────────────────────────────── */
    .q-expansion-item__container {{
        border: 1px solid #e2e8f0;
        border-radius: 0.5rem !important;
        overflow: hidden;
    }}

    /* ── Compact KPI Cards ────────────────────────────────────────── */
    .kpi-card-compact {{
        background: {SURFACE};
        border-radius: 0.5rem;
        padding: 0.375rem 0.625rem;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        border: 1px solid #e2e8f0;
        width: 100%;
        box-sizing: border-box;
        transition: box-shadow 150ms ease, border-color 150ms ease;
    }}
    .kpi-card-compact:hover {{
        box-shadow: 0 2px 8px rgba(0,0,0,0.09);
        border-color: #cbd5e1;
    }}
    .kpi-value-compact {{
        font-size: 0.95rem;
        font-weight: 700;
        color: {PRIMARY};
        letter-spacing: -0.02em;
        line-height: 1.2;
        font-variant-numeric: tabular-nums;
    }}
    .kpi-group-label {{
        font-size: 0.6875rem;
        color: #94a3b8;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 0.125rem;
    }}

    /* ── Utilities ────────────────────────────────────────────────── */
    .fs-heading {{ text-wrap: balance; }}

    /* ── Reduced Motion ───────────────────────────────────────────── */
    @media (prefers-reduced-motion: reduce) {{
        *, *::before, *::after {{
            transition-duration: 0ms !important;
            animation-duration: 0ms !important;
        }}
    }}

    </style>
    """, shared=True)
