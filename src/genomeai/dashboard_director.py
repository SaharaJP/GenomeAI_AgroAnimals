from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import yaml

"""Director dashboards (offline-core).

NOTE (T10-02): PNG snapshot renderer must be fast and deterministic.
We default to a lightweight Pillow-based renderer and keep matplotlib only
as a best-effort fallback.
"""

from core.common.time import utc_isoformat_z, utc_timestamp_compact

from .versioning import ensure_run_dir, write_checksums, write_run_manifest
from .kpi_targets import load_kpi_targets, compute_plan_fact
from .dashboard_insights import compute_top_deviations, load_trend_exceptions_rules, compute_milk_trend_exceptions


def load_director_snapshot_config(cfg_path: Path = Path("configs/reports/director_snapshot_v1.yaml")) -> dict:
    """Load dashboard snapshot rendering config (best effort)."""
    try:
        if cfg_path.exists():
            return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return {}


def _render_director_png(
    *,
    out_path: Path,
    dv: str,
    asof: date,
    kpi_run_id: str,
    plan_fact: pd.DataFrame,
    top_devs: pd.DataFrame,
    milk_ts: pd.DataFrame,
    cfg: dict,
) -> bool:
    """Render a lightweight PNG snapshot (offline-core).

    Default renderer: Pillow (fast, deterministic, no heavy imports).
    Fallback renderer: matplotlib (best-effort).
    """

    png_cfg = (cfg or {}).get("png") or {}
    renderer = str(png_cfg.get("renderer", "pil")).lower()

    # --- Fast path: Pillow ---
    try:
        if renderer in {"pil", "pillow"}:
            from PIL import Image, ImageDraw, ImageFont

            w_px = int(png_cfg.get("width_px", 1600))
            h_px = int(png_cfg.get("height_px", 900))
            n_devs = int(png_cfg.get("top_deviations_rows", 10))
            n_pf = int(png_cfg.get("plan_fact_rows", 12))
            include_plot = bool(png_cfg.get("include_milk_90d_plot", True))

            img = Image.new("RGB", (w_px, h_px), color=(255, 255, 255))
            draw = ImageDraw.Draw(img)
            font_title = ImageFont.load_default()
            font_text = ImageFont.load_default()

            title = f"Director Summary | dv={dv} | asof={asof.isoformat()} | kpi_run={kpi_run_id}"
            draw.text((20, 15), title, fill=(0, 0, 0), font=font_title)
            y = 45

            has_ts = (
                include_plot
                and isinstance(milk_ts, pd.DataFrame)
                and (not milk_ts.empty)
                and ("milk_kg" in milk_ts.columns)
            )
            if has_ts:
                plot_h = int(h_px * 0.28)
                plot_w = w_px - 40
                x0, y0 = 20, y
                x1, y1 = x0 + plot_w, y0 + plot_h
                draw.rectangle([x0, y0, x1, y1], outline=(180, 180, 180), width=1)
                draw.text((x0, y0 - 14), "Milk trend (90d) — sparkline", fill=(0, 0, 0), font=font_text)

                try:
                    ts = milk_ts.copy()
                    ts["milk_kg"] = pd.to_numeric(ts["milk_kg"], errors="coerce").fillna(0.0)
                    vals = ts["milk_kg"].astype(float).tolist()
                    if len(vals) >= 2:
                        vmin, vmax = min(vals), max(vals)
                        if vmax <= vmin:
                            vmax = vmin + 1e-6
                        pts = []
                        for i, v in enumerate(vals):
                            px = x0 + int(i * (plot_w - 1) / (len(vals) - 1))
                            py = y1 - int((v - vmin) * (plot_h - 1) / (vmax - vmin))
                            pts.append((px, py))
                        if pts:
                            draw.line(pts, fill=(30, 120, 200), width=2)
                except Exception:
                    draw.text((x0 + 10, y0 + 10), "Milk trend unavailable", fill=(120, 0, 0), font=font_text)
                y = y1 + 25

            # Table: prefer deviations, fallback to plan-fact
            table_df = None
            table_title = "Top deviations vs targets"
            if isinstance(top_devs, pd.DataFrame) and (not top_devs.empty):
                table_df = top_devs.head(n_devs).copy()
            elif isinstance(plan_fact, pd.DataFrame) and (not plan_fact.empty):
                table_title = "Plan-Fact (sample)"
                table_df = plan_fact.head(n_pf).copy()

            draw.text((20, y), table_title, fill=(0, 0, 0), font=font_text)
            y += 18

            if table_df is None or table_df.empty:
                draw.text((20, y), "No deviations / plan-fact unavailable", fill=(120, 0, 0), font=font_text)
            else:
                cols = list(table_df.columns)[:6]
                header = " | ".join(cols)
                draw.text((20, y), header, fill=(0, 0, 0), font=font_text)
                y += 14
                draw.line([(20, y), (w_px - 20, y)], fill=(200, 200, 200), width=1)
                y += 6
                for _, r in table_df[cols].astype(str).iterrows():
                    line = " | ".join([str(r[c])[:30] for c in cols])
                    draw.text((20, y), line, fill=(0, 0, 0), font=font_text)
                    y += 14
                    if y > h_px - 20:
                        break

            out_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(str(out_path), format="PNG", optimize=True)
            return True
    except Exception:
        # PIL renderer failed -> fall back below
        pass

    # --- Fallback: matplotlib (best-effort) ---
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        w_px = int(png_cfg.get("width_px", 1600))
        h_px = int(png_cfg.get("height_px", 900))
        dpi = int(png_cfg.get("dpi", 150))
        n_devs = int(png_cfg.get("top_deviations_rows", 10))
        n_pf = int(png_cfg.get("plan_fact_rows", 12))
        include_plot = bool(png_cfg.get("include_milk_90d_plot", True))

        fig_w = max(4.0, w_px / float(dpi))
        fig_h = max(3.0, h_px / float(dpi))

        has_ts = include_plot and isinstance(milk_ts, pd.DataFrame) and (not milk_ts.empty) and ("date" in milk_ts.columns)
        if has_ts:
            fig, (ax0, ax1) = plt.subplots(2, 1, figsize=(fig_w, fig_h), dpi=dpi)
        else:
            fig, ax1 = plt.subplots(1, 1, figsize=(fig_w, fig_h), dpi=dpi)
            ax0 = None

        fig.suptitle(f"Director Summary — data_version={dv} | as-of={asof.isoformat()} | kpi_run={kpi_run_id}", fontsize=12)

        if ax0 is not None:
            ax0.set_title("Milk (90d) — dm_milkings_daily.csv", fontsize=10)
            ts = milk_ts.copy()
            ts["date"] = pd.to_datetime(ts["date"], errors="coerce")
            ts["milk_kg"] = pd.to_numeric(ts.get("milk_kg"), errors="coerce")
            ts = ts.dropna(subset=["date"]).sort_values("date")
            ax0.plot(ts["date"], ts["milk_kg"].fillna(0.0).values)
            ax0.set_ylabel("milk_kg")
            ax0.grid(True, alpha=0.2)

        ax1.axis("off")
        table_df = None
        title = "Top deviations vs targets"
        if isinstance(top_devs, pd.DataFrame) and (not top_devs.empty):
            table_df = top_devs.copy().head(n_devs)
        elif isinstance(plan_fact, pd.DataFrame) and (not plan_fact.empty):
            title = "Plan-Fact (sample)"
            table_df = plan_fact.copy().head(n_pf)

        if table_df is None or table_df.empty:
            ax1.text(0.01, 0.9, "No deviations / plan-fact unavailable", fontsize=11)
        else:
            cols = list(table_df.columns)[:6]
            t = table_df[cols].astype(str)
            ax1.text(0.01, 0.98, title, fontsize=11, va="top")
            tbl = ax1.table(cellText=t.values, colLabels=cols, loc="upper left", cellLoc="left", colLoc="left")
            tbl.auto_set_font_size(False)
            tbl.set_fontsize(8)
            tbl.scale(1, 1.2)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        fig.savefig(str(out_path), dpi=dpi)
        plt.close(fig)
        return True
    except Exception:
        return False

@dataclass
class DirectorSummaryInputs:
    data_version: str
    artifacts_dir: Path
    input_dir: Optional[Path] = None  # optional canonical/fixtures dir
    kpi_run_id: Optional[str] = None  # if omitted, auto-detect latest KPI run
    asof_date: Optional[date] = None

def _find_latest_kpi_run(artifacts_dir: Path, data_version: str) -> Optional[str]:
    runs_dir = artifacts_dir / data_version / "runs"
    if not runs_dir.exists():
        return None
    candidates: List[Tuple[float, str]] = []
    for p in runs_dir.iterdir():
        if not p.is_dir():
            continue
        kpi_wide = p / "kpi" / "kpi_wide.csv"
        if kpi_wide.exists():
            candidates.append((kpi_wide.stat().st_mtime, p.name))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]



def find_latest_dashboard_run(artifacts_dir: Path, data_version: str, dashboard_kind: str = "director_summary") -> Optional[str]:
    """Find latest dashboard snapshot run for a given data_version.

    Looks for artifacts/<dv>/runs/<run_id>/dashboards/<dashboard_kind>/dashboard_summary.json.
    Returns run_id with the most recent dashboard_summary.json mtime.

    This helper is used by web-cabinet to *read* snapshot artifacts without recomputing.
    """
    runs_dir = artifacts_dir / data_version / "runs"
    if not runs_dir.exists():
        return None
    candidates: List[Tuple[float, str]] = []
    for p in runs_dir.iterdir():
        if not p.is_dir():
            continue
        summ = p / "dashboards" / dashboard_kind / "dashboard_summary.json"
        if summ.exists():
            candidates.append((summ.stat().st_mtime, p.name))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]

def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)

def load_kpi_outputs(*, artifacts_dir: Path, data_version: str, kpi_run_id: Optional[str] = None) -> Tuple[str, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (kpi_run_id, kpi_long, kpi_wide, kpi_alerts)."""
    rid = kpi_run_id or _find_latest_kpi_run(artifacts_dir, data_version)
    if not rid:
        raise FileNotFoundError(f"No KPI run found for data_version={data_version} in {artifacts_dir}")
    run_root = artifacts_dir / data_version / "runs" / rid / "kpi"
    kpi_long = _load_csv(run_root / "kpi_long.csv")
    kpi_wide = _load_csv(run_root / "kpi_wide.csv")
    alerts = _load_csv(run_root / "kpi_alerts.csv")
    return rid, kpi_long, kpi_wide, alerts

def load_kpi_dictionary(cfg_path: Path) -> Dict[str, dict]:
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    out = {}
    for k in cfg.get("kpis", []):
        out[k["kpi_id"]] = k
    return out

def compute_milk_trend(*, input_dir: Path, days: int, asof: date) -> pd.DataFrame:
    """Daily total milk_kg for last N days ending at asof (inclusive)."""
    m = _load_csv(input_dir / "dm_milkings_daily.csv")
    if m.empty:
        return pd.DataFrame(columns=["date", "milk_kg"])
    m["date"] = pd.to_datetime(m["date"], errors="coerce").dt.date
    start = asof - timedelta(days=days-1)
    sub = m.loc[(m["date"] >= start) & (m["date"] <= asof)].copy()
    sub.loc[:, "milk_kg"] = pd.to_numeric(sub["milk_kg"], errors="coerce")
    ts = sub.groupby("date", as_index=False)["milk_kg"].sum().sort_values("date")
    return ts


def compute_milk_trend_windows(*, input_dir: Path, asof: date, windows: Tuple[int, ...] = (7, 30, 90)) -> pd.DataFrame:
    """Compute plan-fact-like window stats for milk totals.

    Returns a small table with current vs previous window sums and % change.
    Uses dm_milkings_daily.csv from input_dir (canonical/fixtures).

    Columns:
      window_days, cur_start, cur_end, cur_sum_kg, prev_start, prev_end, prev_sum_kg, change_kg, change_pct, source_table, source_path
    """

    out_cols = [
        "window_days",
        "cur_start",
        "cur_end",
        "cur_sum_kg",
        "prev_start",
        "prev_end",
        "prev_sum_kg",
        "change_kg",
        "change_pct",
        "source_table",
        "source_path",
    ]

    if input_dir is None or not Path(input_dir).exists():
        return pd.DataFrame(columns=out_cols)

    try:
        max_w = int(max(windows))
    except Exception:
        max_w = 90

    # Need up to 2*max_w days to compare current and previous windows.
    ts = compute_milk_trend(input_dir=Path(input_dir), days=max_w * 2, asof=asof)
    if ts.empty:
        return pd.DataFrame(columns=out_cols)

    ts = ts.copy()
    ts["date"] = pd.to_datetime(ts["date"], errors="coerce").dt.date
    ts["milk_kg"] = pd.to_numeric(ts["milk_kg"], errors="coerce")

    # Build a fast lookup (missing dates => 0).
    m = {d: float(v) for d, v in zip(ts["date"].tolist(), ts["milk_kg"].fillna(0.0).tolist()) if d is not None}

    rows = []
    for w in windows:
        w = int(w)
        if w <= 0:
            continue
        cur_start = asof - timedelta(days=w - 1)
        cur_end = asof
        prev_end = cur_start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=w - 1)

        cur_sum = 0.0
        for i in range(w):
            d = cur_start + timedelta(days=i)
            cur_sum += float(m.get(d, 0.0))

        prev_sum = 0.0
        for i in range(w):
            d = prev_start + timedelta(days=i)
            prev_sum += float(m.get(d, 0.0))

        change = cur_sum - prev_sum
        if prev_sum > 0:
            change_pct = change / prev_sum
        else:
            change_pct = float("nan")

        rows.append(
            {
                "window_days": w,
                "cur_start": cur_start.isoformat(),
                "cur_end": cur_end.isoformat(),
                "cur_sum_kg": cur_sum,
                "prev_start": prev_start.isoformat(),
                "prev_end": prev_end.isoformat(),
                "prev_sum_kg": prev_sum,
                "change_kg": change,
                "change_pct": change_pct,
                "source_table": "dm_milkings_daily",
                "source_path": str((Path(input_dir) / "dm_milkings_daily.csv").as_posix()),
            }
        )

    return pd.DataFrame(rows, columns=out_cols)

def compute_alerts_trend(*, input_dir: Path, days: int, asof: date) -> pd.DataFrame:
    a = _load_csv(input_dir / "dm_alerts.csv")
    if a.empty:
        return pd.DataFrame(columns=["date", "open_alerts"])
    a["created_at"] = pd.to_datetime(a.get("created_at"), errors="coerce")
    a["date"] = a["created_at"].dt.date
    start = asof - timedelta(days=days-1)
    sub = a[(a["date"] >= start) & (a["date"] <= asof)]
    # count new alerts per day
    ts = sub.groupby("date", as_index=False).size().rename(columns={"size":"open_alerts"}).sort_values("date")
    return ts

def export_director_summary(
    *,
    inputs: DirectorSummaryInputs,
    run_id: Optional[str] = None,
    kpi_cfg_path: Optional[Path] = None,
    targets_cfg_path: Path = Path("configs/kpi/kpi_targets_v1.yaml"),
    config_override_dir: Optional[Path] = None,
    snapshot_cfg_path: Path = Path("configs/reports/director_snapshot_v1.yaml"),
    trend_exceptions_cfg_path: Path = Path("configs/kpi/kpi_trend_exceptions_v1.yaml"),
) -> Path:
    """Generate director summary export (xlsx + pdf + png) and return dashboard run root."""
    artifacts_dir = inputs.artifacts_dir
    dv = inputs.data_version
    asof = inputs.asof_date or date.today()
    kpi_run_id, kpi_long, kpi_wide, kpi_alerts = load_kpi_outputs(artifacts_dir=artifacts_dir, data_version=dv, kpi_run_id=inputs.kpi_run_id)

    dash_run = run_id or f"dash_{utc_timestamp_compact()}"
    run_root = ensure_run_dir(artifacts_dir, dv, dash_run)
    out_dir = run_root / "dashboards" / "director_summary"
    out_dir.mkdir(parents=True, exist_ok=True)

    # plan-fact (targets vs actual)
    try:
        targets_cfg = load_kpi_targets(cfg_path=targets_cfg_path, override_dir=config_override_dir)
        plan_fact = compute_plan_fact(kpi_long, targets_cfg=targets_cfg, data_version=dv, kpi_run_id=kpi_run_id)
    except Exception as e:
        # human-readable error and keep export usable
        plan_fact = pd.DataFrame(
            {
                "error": [
                    f"plan-fact не рассчитан: {e}. "
                    f"Проверьте конфиг целей {targets_cfg_path} (override_dir={config_override_dir})."
                ]
            }
        )
    plan_fact_path = out_dir / "kpi_plan_fact.csv"
    try:
        plan_fact.to_csv(plan_fact_path, index=False)
    except Exception:
        pass



    # top deviations (plan-fact vs targets) + explanations
    top_devs_path = out_dir / "kpi_top_deviations.csv"
    try:
        kpi_cfg = load_kpi_dictionary(kpi_cfg_path or Path("configs/kpi/kpi_v2.yaml"))
        top_devs = compute_top_deviations(plan_fact, kpi_cfg=kpi_cfg, top_n=12)
    except Exception as e:
        top_devs = pd.DataFrame({"error": [f"top deviations не рассчитаны: {e}"]})
    try:
        top_devs.to_csv(top_devs_path, index=False)
    except Exception:
        pass

    # trends 7/30/90 for milk (best-effort, needs input_dir)
    milk_ts = pd.DataFrame()
    milk_windows = pd.DataFrame()
    milk_exceptions = pd.DataFrame()
    milk_ts_path = out_dir / "milk_trend_90d.csv"
    milk_windows_path = out_dir / "milk_trend_windows.csv"
    milk_exceptions_path = out_dir / "milk_trend_exceptions.csv"
    if inputs.input_dir and Path(inputs.input_dir).exists():
        try:
            milk_ts = compute_milk_trend(input_dir=Path(inputs.input_dir), days=90, asof=asof)
            milk_windows = compute_milk_trend_windows(input_dir=Path(inputs.input_dir), asof=asof, windows=(7, 30, 90))
            milk_ts.to_csv(milk_ts_path, index=False)
            milk_windows.to_csv(milk_windows_path, index=False)

            # Trend exceptions (top window deltas) with explanations + run_id
            # Always write a CSV (possibly empty) to keep outputs stable for UI.
            try:
                rules = load_trend_exceptions_rules(trend_exceptions_cfg_path)
                milk_exceptions = compute_milk_trend_exceptions(
                    milk_windows,
                    rules=rules,
                    data_version=dv,
                    dashboard_run_id=dash_run,
                )
            except Exception:
                milk_exceptions = pd.DataFrame(columns=[
                    "kpi_id",
                    "window_days",
                    "severity",
                    "change_pct",
                    "change_kg",
                    "cur_sum_kg",
                    "prev_sum_kg",
                    "cur_start",
                    "cur_end",
                    "prev_start",
                    "prev_end",
                    "source_table",
                    "source_path",
                    "data_version",
                    "dashboard_run_id",
                    "explanation",
                ])
            try:
                milk_exceptions.to_csv(milk_exceptions_path, index=False)
            except Exception:
                pass
        except Exception as e:
            milk_windows = pd.DataFrame({"error": [f"trends не рассчитаны: {e}"]})
            try:
                milk_windows.to_csv(milk_windows_path, index=False)
            except Exception:
                pass

    # export xlsx
    xlsx_path = out_dir / "director_summary.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as xw:
        kpi_wide.to_excel(xw, index=False, sheet_name="kpi_wide")
        kpi_long.to_excel(xw, index=False, sheet_name="kpi_long")
        kpi_alerts.to_excel(xw, index=False, sheet_name="kpi_alerts")
        # Director 3.0: plan-fact
        plan_fact.to_excel(xw, index=False, sheet_name="plan_fact")
        # Director 3.0: deviations + trends
        try:
            top_devs.to_excel(xw, index=False, sheet_name="top_deviations")
        except Exception:
            pass
        try:
            if isinstance(milk_ts, pd.DataFrame) and (not milk_ts.empty):
                milk_ts.to_excel(xw, index=False, sheet_name="milk_90d")
        except Exception:
            pass
        try:
            if isinstance(milk_windows, pd.DataFrame) and (not milk_windows.empty):
                milk_windows.to_excel(xw, index=False, sheet_name="milk_windows")
        except Exception:
            pass
        try:
            # Write even an empty sheet when trends input is available — stable template for the user.
            if isinstance(milk_exceptions, pd.DataFrame) and inputs.input_dir and Path(inputs.input_dir).exists():
                milk_exceptions.to_excel(xw, index=False, sheet_name="milk_exceptions")
        except Exception:
            pass

    # export pdf (minimal, no charts)
    pdf_path = out_dir / "director_summary.pdf"
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        c = canvas.Canvas(str(pdf_path), pagesize=A4)
        w, h = A4
        y = h - 40
        c.setFont("Helvetica-Bold", 14)
        c.drawString(40, y, f"Director Summary (data_version={dv})")
        y -= 18
        c.setFont("Helvetica", 10)
        c.drawString(40, y, f"As-of: {asof.isoformat()}  |  KPI run: {kpi_run_id}")
        y -= 24
        c.setFont("Helvetica-Bold", 11)
        c.drawString(40, y, "Top KPI alerts (up to 20):")
        y -= 16
        c.setFont("Helvetica", 9)
        if not kpi_alerts.empty:
            cols = [c for c in ["farm_id","kpi_id","severity","value","unit","message"] if c in kpi_alerts.columns]
            for _, row in kpi_alerts.head(20).iterrows():
                line = " | ".join(str(row.get(col,""))[:40] for col in cols)
                c.drawString(40, y, line)
                y -= 12
                if y < 60:
                    c.showPage()
                    y = h - 40
                    c.setFont("Helvetica", 9)
        else:
            c.drawString(40, y, "No KPI alerts.")

        # Top deviations (up to 10)
        y -= 18
        if y < 80:
            c.showPage()
            y = h - 40
        c.setFont("Helvetica-Bold", 11)
        c.drawString(40, y, "Top deviations vs targets (up to 10):")
        y -= 16
        c.setFont("Helvetica", 9)
        try:
            if isinstance(top_devs, pd.DataFrame) and (not top_devs.empty) and ("kpi_id" in top_devs.columns):
                cols2 = [c for c in ["farm_id", "kpi_id", "status", "delta_pct"] if c in top_devs.columns]
                for _, row in top_devs.head(10).iterrows():
                    line = " | ".join(str(row.get(col, ""))[:50] for col in cols2)
                    c.drawString(40, y, line)
                    y -= 12
                    if y < 60:
                        c.showPage()
                        y = h - 40
                        c.setFont("Helvetica", 9)
            else:
                c.drawString(40, y, "No deviations.")
        except Exception:
            c.drawString(40, y, "No deviations.")

        c.save()
    except Exception:
        # graceful fallback: keep xlsx only
        pdf_path = Path("")

    # export png snapshot (best-effort)
    png_cfg_path = Path(snapshot_cfg_path)
    png_path = out_dir / "director_summary.png"
    png_ok = _render_director_png(
        out_path=png_path,
        dv=dv,
        asof=asof,
        kpi_run_id=kpi_run_id,
        plan_fact=plan_fact if isinstance(plan_fact, pd.DataFrame) else pd.DataFrame(),
        top_devs=top_devs if isinstance(top_devs, pd.DataFrame) else pd.DataFrame(),
        milk_ts=milk_ts if isinstance(milk_ts, pd.DataFrame) else pd.DataFrame(),
        cfg=load_director_snapshot_config(png_cfg_path),
    )
    if not png_ok:
        try:
            if png_path.exists():
                png_path.unlink()
        except Exception:
            pass

    summary = {
        "data_version": dv,
        "run_id": dash_run,
        "step": "dashboard.director_summary",
        "asof_date": asof.isoformat(),
        "inputs": {
            "kpi_run_id": kpi_run_id,
        },
        "outputs": {
            "xlsx": str(xlsx_path.relative_to(run_root)),
            "pdf": str(pdf_path.relative_to(run_root)) if pdf_path and pdf_path.exists() else None,
            "png": str(png_path.relative_to(run_root)) if png_path.exists() else None,
            "kpi_plan_fact_csv": str(plan_fact_path.relative_to(run_root)) if plan_fact_path.exists() else None,
            "kpi_top_deviations_csv": str(top_devs_path.relative_to(run_root)) if top_devs_path.exists() else None,
            "milk_trend_90d_csv": str(milk_ts_path.relative_to(run_root)) if milk_ts_path.exists() else None,
            "milk_trend_windows_csv": str(milk_windows_path.relative_to(run_root)) if milk_windows_path.exists() else None,
            "milk_trend_exceptions_csv": str(milk_exceptions_path.relative_to(run_root)) if milk_exceptions_path.exists() else None,
        },
    }

    (out_dir / "dashboard_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    write_checksums(run_root=run_root)
    manifest = {
        "schema_version": "1.0",
        "data_version": dv,
        "run_id": dash_run,
        "step": "dashboard.director_summary",
        "created_at": utc_isoformat_z(),
        "inputs": {"kpi_run_id": kpi_run_id},
        "outputs": {
            "director_summary_xlsx": str(xlsx_path.relative_to(run_root)),
            "director_summary_pdf": str(pdf_path.relative_to(run_root)) if pdf_path and pdf_path.exists() else None,
            "director_summary_png": str(png_path.relative_to(run_root)) if png_path.exists() else None,
            "kpi_plan_fact_csv": str(plan_fact_path.relative_to(run_root)) if plan_fact_path.exists() else None,
            "kpi_top_deviations_csv": str(top_devs_path.relative_to(run_root)) if top_devs_path.exists() else None,
            "milk_trend_90d_csv": str(milk_ts_path.relative_to(run_root)) if milk_ts_path.exists() else None,
            "milk_trend_windows_csv": str(milk_windows_path.relative_to(run_root)) if milk_windows_path.exists() else None,
            "milk_trend_exceptions_csv": str(milk_exceptions_path.relative_to(run_root)) if milk_exceptions_path.exists() else None,
            "dashboard_summary_json": str((out_dir / "dashboard_summary.json").relative_to(run_root)),
        },
        "lineage": {
            "kpi_run_id": kpi_run_id,
            "kpi_config": str(kpi_cfg_path or Path("configs/kpi/kpi_v2.yaml")),
            "targets_config": str(targets_cfg_path),
            "targets_override_dir": str(config_override_dir) if config_override_dir else None,
            "snapshot_png_config": str(png_cfg_path),
            "trend_exceptions_config": str(trend_exceptions_cfg_path),
        },
    }
    write_checksums(run_root=run_root)
    write_run_manifest(run_root=run_root, manifest=manifest)
    return run_root
