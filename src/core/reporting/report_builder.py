from __future__ import annotations

from pathlib import Path
from typing import Mapping, MutableMapping, Optional

from genomeai.versioning import compute_data_version, write_json


def persist_fact_pack_bundle(
    *,
    out_dir: Path,
    fact_pack: MutableMapping[str, object],
    report_version: Optional[str] = None,
) -> dict[str, str]:
    """Persist fact_pack.json and return stable metadata used by summaries.

    Behavior intentionally matches existing legacy flows:
    1) write fact_pack.json,
    2) compute hash from serialized content,
    3) attach fact_pack_hash into payload,
    4) rewrite fact_pack.json.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fact_pack_path = out_dir / "fact_pack.json"
    write_json(fact_pack_path, fact_pack)
    fact_pack_hash = compute_data_version(fact_pack_path)
    fact_pack["fact_pack_hash"] = fact_pack_hash
    write_json(fact_pack_path, fact_pack)
    return {
        "fact_pack": str(fact_pack_path.resolve()),
        "fact_pack_hash": str(fact_pack_hash),
    }


def render_html_from_md(md_text: str) -> str:
    """Minimal markdown->HTML renderer kept intentionally deterministic."""
    html_lines: list[str] = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'>",
        "<style>body{font-family:Arial,Helvetica,sans-serif;margin:24px;} pre{background:#f6f8fa;padding:12px;overflow:auto;} table{border-collapse:collapse;} td,th{border:1px solid #ddd;padding:6px;} h1,h2,h3{margin-top:18px;}</style>",
        "</head><body>",
    ]
    in_code = False
    for line in md_text.splitlines():
        if line.strip().startswith("```"):
            if not in_code:
                html_lines.append("<pre>")
                in_code = True
            else:
                html_lines.append("</pre>")
                in_code = False
            continue
        if in_code:
            html_lines.append(line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
            continue
        if line.startswith("### "):
            html_lines.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            html_lines.append(f"<h1>{line[2:]}</h1>")
        elif line.strip() == "---":
            html_lines.append("<hr/>")
        elif line.strip().startswith("|") and line.strip().endswith("|"):
            html_lines.append(f"<pre>{line}</pre>")
        elif line.strip() == "":
            html_lines.append("<br/>")
        else:
            html_lines.append(f"<p>{line}</p>")
    if in_code:
        html_lines.append("</pre>")
    html_lines.append("</body></html>")
    return "\n".join(html_lines)


def render_pdf_simple(*, title: str, md_text: str, out_path: Path) -> bool:
    try:
        from reportlab.lib.pagesizes import A4  # type: ignore
        from reportlab.lib.units import cm  # type: ignore
        from reportlab.pdfbase import pdfmetrics  # type: ignore
        from reportlab.pdfbase.ttfonts import TTFont  # type: ignore
        from reportlab.pdfgen import canvas  # type: ignore
    except Exception:
        return False

    try:
        pdfmetrics.registerFont(TTFont("DejaVu", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
        font_name = "DejaVu"
    except Exception:
        font_name = "Helvetica"

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=A4)
    _w, h = A4
    x = 2 * cm
    y = h - 2 * cm
    c.setFont(font_name, 14)
    c.drawString(x, y, title[:120])
    y -= 1 * cm
    c.setFont(font_name, 10)
    for raw in md_text.splitlines():
        line = raw.strip("\n")
        if y < 2 * cm:
            c.showPage()
            y = h - 2 * cm
            c.setFont(font_name, 10)
        c.drawString(x, y, line[:140])
        y -= 0.45 * cm
    c.save()
    return True


def write_markdown_report_bundle(
    *,
    exports_dir: Path,
    markdown_by_audience: Mapping[str, str],
    pdf_titles: Optional[Mapping[str, str]] = None,
) -> dict[str, str]:
    """Write report_<audience>.md/html/pdf files with deterministic names."""
    exports_dir = Path(exports_dir)
    exports_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, str] = {}
    titles = dict(pdf_titles or {})
    for audience, md_text in markdown_by_audience.items():
        base_name = f"report_{audience}"
        md_path = exports_dir / f"{base_name}.md"
        md_path.write_text(md_text, encoding="utf-8")

        html_path = exports_dir / f"{base_name}.html"
        html_path.write_text(render_html_from_md(md_text), encoding="utf-8")

        pdf_path = exports_dir / f"{base_name}.pdf"
        pdf_ok = render_pdf_simple(
            title=str(titles.get(audience) or f"Report {audience}"),
            md_text=md_text,
            out_path=pdf_path,
        )

        outputs[f"{audience}_md"] = str(md_path.resolve())
        outputs[f"{audience}_html"] = str(html_path.resolve())
        outputs[f"{audience}_pdf"] = str(pdf_path.resolve()) if (pdf_ok and pdf_path.exists()) else "NA"
    return outputs
