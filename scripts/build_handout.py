#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph
from pypdf import PdfReader


W, H = A4
MARGIN_X = 10 * mm
HEADER_H = 8 * mm
FOOTER_H = 8 * mm
GAP = 7 * mm
PAGE_BODY_H = H - HEADER_H - FOOTER_H
PAIR_BLOCK_H = (PAGE_BODY_H - GAP) / 2
SINGLE_BLOCK_H = PAGE_BODY_H
PAIR_MIN_PT = 8.7
SINGLE_MIN_PT = 9.3
INK = colors.HexColor("#18323A")
MUTED = colors.HexColor("#61747B")
DIVIDER = colors.HexColor("#AEBBBA")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a density-adaptive A4 transcript handout.")
    parser.add_argument("--slides-pdf", required=True, type=Path)
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--qa-dir", type=Path, help="Render final pages as JPEGs here.")
    parser.add_argument("--font-regular", type=Path)
    parser.add_argument("--font-bold", type=Path)
    return parser.parse_args()


def find_font(explicit: Path | None, bold: bool = False) -> Path:
    if explicit:
        if not explicit.exists():
            raise FileNotFoundError(explicit)
        return explicit
    home = Path.home()
    candidates = ([
        home / "Library/Fonts/AlibabaPuHuiTi-3-85-Bold.ttf",
        home / "Library/Fonts/NotoSansCJKsc-Bold.otf",
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    ] if bold else [
        home / "Library/Fonts/AlibabaPuHuiTi-3-55-Regular.ttf",
        home / "Library/Fonts/NotoSansCJKsc-Regular.otf",
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ])
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise RuntimeError("No CJK font found; pass --font-regular and --font-bold.")


def run(command: list[str]) -> None:
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout or "Command failed")


def validate_mapping(mapping: dict, slide_count: int) -> list[dict]:
    pages = mapping.get("pages")
    if not isinstance(pages, list) or len(pages) != slide_count:
        count = len(pages) if isinstance(pages, list) else 0
        raise ValueError(f"Mapping has {count} pages; slides have {slide_count}.")
    if [item.get("page") for item in pages] != list(range(1, slide_count + 1)):
        raise ValueError("Mapping page numbers must be consecutive and start at 1.")
    for page in pages:
        for key in ("title", "transcript", "time", "note"):
            if not isinstance(page.get(key, ""), str):
                raise TypeError(f"Page {page['page']} field {key!r} must be a string.")
    cleaned = mapping.get("cleaned_transcript", "")
    placed = "".join(page.get("transcript", "") for page in pages)
    if cleaned != placed:
        raise ValueError(
            f"Transcript coverage mismatch: placed {len(placed)} characters, expected {len(cleaned)}."
        )
    return pages


def body_style(size: float) -> ParagraphStyle:
    return ParagraphStyle(
        f"body-{size:.1f}", fontName="CN", fontSize=size,
        leading=size * 1.38, textColor=INK, alignment=TA_LEFT,
        splitLongWords=True, wordWrap="CJK", spaceAfter=0,
    )


def make_paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(html.escape(text).replace("\n", "<br/>"), style)


def paragraph_height(text: str, style: ParagraphStyle, width: float) -> float:
    _, used = make_paragraph(text, style).wrap(width, 1000 * mm)
    return used


def display_text(page: dict) -> str:
    return page.get("transcript", "") or page.get("note") or (
        "现有逐字稿中没有找到本页可单独对应的讲解。"
    )


def layout_available(top: float, height: float, image_width: float) -> float:
    image_h = image_width * 9 / 16
    text_top = top - 8 * mm - image_h - 5.1 * mm
    return text_top - (top - height + 1.5 * mm)


def choose_layout(
    text: str, width: float, top: float, height: float, mode: str
) -> tuple[float, ParagraphStyle] | None:
    length = len(text)
    if mode == "pair":
        if length <= 100:
            preferred_width, preferred_type = 182, 9.5
        elif length <= 250:
            preferred_width, preferred_type = 176, 9.3
        elif length <= 400:
            preferred_width, preferred_type = 168, 9.0
        elif length <= 520:
            preferred_width, preferred_type = 158, 8.7
        else:
            preferred_width, preferred_type = 148, 8.7
        min_width, min_type = 134, PAIR_MIN_PT
        type_options = (9.5, 9.3, 9.0, 8.7)
    elif mode == "single":
        if length <= 250:
            preferred_width, preferred_type = 182, 10.0
        elif length <= 700:
            preferred_width, preferred_type = 178, 9.8
        elif length <= 1200:
            preferred_width, preferred_type = 170, 9.5
        else:
            preferred_width, preferred_type = 162, 9.3
        min_width, min_type = 152, SINGLE_MIN_PT
        type_options = (10.0, 9.8, 9.5, 9.3)
    else:
        raise ValueError(f"Unknown layout mode: {mode}")

    sizes = [preferred_type] + [x for x in type_options if min_type <= x < preferred_type]
    for size in sizes:
        style = body_style(size)
        for width_mm in range(preferred_width, min_width - 1, -2):
            image_width = width_mm * mm
            available = layout_available(top, height, image_width)
            if paragraph_height(text, style, width) <= available:
                return image_width, style
    return None


def split_to_fit(
    text: str, style: ParagraphStyle, width: float, available: float
) -> tuple[str, str]:
    if paragraph_height(text, style, width) <= available:
        return text, ""
    low, high = 1, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if paragraph_height(text[:middle], style, width) <= available:
            low = middle
        else:
            high = middle - 1
    cut = low
    floor = max(1, int(cut * 0.72))
    for index in range(cut, floor, -1):
        if text[index - 1] in "。！？；\n.!?;":
            cut = index
            break
    if cut <= 0:
        raise RuntimeError("A transcript fragment cannot fit on an empty page.")
    return text[:cut], text[cut:]


def draw_slide(c: Canvas, image: Path, x: float, y_top: float, width: float) -> float:
    with PILImage.open(image) as im:
        image_width, image_height = im.size
    height = width * 9 / 16
    scale = min(width / image_width, height / image_height)
    draw_width, draw_height = image_width * scale, image_height * scale
    c.drawImage(
        str(image), x + (width - draw_width) / 2, y_top - (height + draw_height) / 2,
        draw_width, draw_height, preserveAspectRatio=True, mask="auto",
    )
    return height


def draw_block(
    c: Canvas,
    page: dict,
    image: Path,
    top: float,
    height: float,
    layout: tuple[float, ParagraphStyle],
    text: str | None = None,
    title_suffix: str = "",
) -> None:
    inner_x = MARGIN_X
    inner_width = W - 2 * MARGIN_X
    title = page.get("title") or f"Slide {page['page']}"
    c.setFillColor(INK)
    c.setFont("CN-B", 9.2)
    c.drawString(inner_x, top - 4.5 * mm, f"PPT {page['page']:03d}  ·  {title}{title_suffix}")

    shown_text = display_text(page) if text is None else text
    image_width, style = layout
    media_top = top - 8 * mm
    image_height = draw_slide(
        c, image, inner_x + (inner_width - image_width) / 2, media_top, image_width
    )

    note_y = media_top - image_height - 2.4 * mm
    c.setFillColor(MUTED)
    c.setFont("CN", 6.8)
    c.drawString(inner_x, note_y, page.get("time") or "无独立讲解")
    text_top = note_y - 2.7 * mm
    available = text_top - (top - height + 1.5 * mm)
    needed = paragraph_height(shown_text, style, inner_width)
    if needed > available + 0.1:
        raise RuntimeError(
            f"Text overflow on slide {page['page']}: {needed:.1f} > {available:.1f}. "
            "The adaptive layout plan is inconsistent."
        )
    text_object = make_paragraph(shown_text, style)
    _, used = text_object.wrap(inner_width, available)
    text_object.drawOn(c, inner_x, text_top - used)


def draw_continuation(
    c: Canvas, page: dict, text: str, continuation_number: int, total: int
) -> None:
    inner_x = MARGIN_X
    inner_width = W - 2 * MARGIN_X
    title = page.get("title") or f"Slide {page['page']}"
    c.setFillColor(INK)
    c.setFont("CN-B", 10.0)
    c.drawString(
        inner_x,
        H - HEADER_H - 4.5 * mm,
        f"PPT {page['page']:03d}  ·  {title}  /  讲稿续页 {continuation_number}/{total}",
    )
    c.setFillColor(MUTED)
    c.setFont("CN", 6.8)
    c.drawString(inner_x, H - HEADER_H - 9 * mm, page.get("time") or "无独立讲解")
    style = body_style(SINGLE_MIN_PT)
    available = PAGE_BODY_H - 15 * mm
    text_object = make_paragraph(text, style)
    _, used = text_object.wrap(inner_width, available)
    if used > available + 0.1:
        raise RuntimeError(f"Continuation overflow on slide {page['page']}.")
    text_object.drawOn(c, inner_x, H - HEADER_H - 13 * mm - used)


def continuation_chunks(text: str, width: float) -> list[str]:
    style = body_style(SINGLE_MIN_PT)
    available = PAGE_BODY_H - 15 * mm
    chunks: list[str] = []
    remaining = text
    while remaining:
        chunk, remaining = split_to_fit(remaining, style, width, available)
        chunks.append(chunk)
    return chunks


def build_layout_plan(pages: list[dict]) -> list[dict]:
    inner_width = W - 2 * MARGIN_X
    top = H - HEADER_H
    plan: list[dict] = []
    index = 0
    while index < len(pages):
        current = pages[index]
        current_pair = choose_layout(
            display_text(current), inner_width, top, PAIR_BLOCK_H, "pair"
        )
        next_pair = None
        if index + 1 < len(pages):
            next_pair = choose_layout(
                display_text(pages[index + 1]), inner_width, top, PAIR_BLOCK_H, "pair"
            )
        if current_pair is not None and next_pair is not None:
            plan.append({
                "kind": "pair",
                "items": [
                    {"index": index, "layout": current_pair},
                    {"index": index + 1, "layout": next_pair},
                ],
            })
            index += 2
            continue

        full_text = display_text(current)
        single_layout = choose_layout(
            full_text, inner_width, top, SINGLE_BLOCK_H, "single"
        )
        if single_layout is not None:
            plan.append({
                "kind": "single",
                "items": [{"index": index, "layout": single_layout, "text": full_text}],
            })
        else:
            primary_layout = (158 * mm, body_style(SINGLE_MIN_PT))
            available = layout_available(top, SINGLE_BLOCK_H, primary_layout[0])
            primary_text, remaining = split_to_fit(
                full_text, primary_layout[1], inner_width, available
            )
            plan.append({
                "kind": "single",
                "items": [{
                    "index": index,
                    "layout": primary_layout,
                    "text": primary_text,
                    "continued": True,
                }],
            })
            chunks = continuation_chunks(remaining, inner_width)
            for number, chunk in enumerate(chunks, start=1):
                plan.append({
                    "kind": "continuation",
                    "index": index,
                    "text": chunk,
                    "number": number,
                    "total": len(chunks),
                })
        index += 1
    return plan


def validate_layout_plan(plan: list[dict], pages: list[dict]) -> None:
    placed = ["" for _ in pages]
    for sheet in plan:
        if sheet["kind"] == "pair":
            for item in sheet["items"]:
                placed[item["index"]] += display_text(pages[item["index"]])
        elif sheet["kind"] == "single":
            item = sheet["items"][0]
            placed[item["index"]] += item["text"]
        else:
            placed[sheet["index"]] += sheet["text"]
    for index, page in enumerate(pages):
        if placed[index] != display_text(page):
            raise RuntimeError(
                f"Adaptive layout lost or duplicated text for slide {page['page']}."
            )


def render_source(pdf: Path, directory: Path) -> list[Path]:
    if not shutil.which("pdftoppm"):
        raise RuntimeError("pdftoppm is required to render the source slides.")
    prefix = directory / "slide"
    run(["pdftoppm", "-jpeg", "-r", "160", str(pdf), str(prefix)])
    images = sorted(directory.glob("slide-*.jpg"))
    if not images:
        raise RuntimeError("Source slide rendering produced no images.")
    return images


def build(args: argparse.Namespace) -> None:
    regular = find_font(args.font_regular)
    bold = find_font(args.font_bold, bold=True)
    pdfmetrics.registerFont(TTFont("CN", str(regular)))
    pdfmetrics.registerFont(TTFont("CN-B", str(bold)))

    mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
    slide_count = len(PdfReader(str(args.slides_pdf)).pages)
    pages = validate_mapping(mapping, slide_count)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="slides-transcript-") as temporary:
        images = render_source(args.slides_pdf, Path(temporary))
        if len(images) != slide_count:
            raise RuntimeError(f"Rendered {len(images)} slides, expected {slide_count}.")
        plan = build_layout_plan(pages)
        validate_layout_plan(plan, pages)
        canvas = Canvas(str(args.output), pagesize=A4, pageCompression=1)
        canvas.setTitle(mapping.get("title") or args.output.stem)
        for sheet_number, sheet in enumerate(plan, start=1):
            canvas.setFillColor(colors.white)
            canvas.rect(0, 0, W, H, fill=1, stroke=0)
            top = H - HEADER_H
            if sheet["kind"] == "pair":
                first, second = sheet["items"]
                draw_block(
                    canvas, pages[first["index"]], images[first["index"]],
                    top, PAIR_BLOCK_H, first["layout"],
                )
                draw_block(
                    canvas, pages[second["index"]], images[second["index"]],
                    top - PAIR_BLOCK_H - GAP, PAIR_BLOCK_H, second["layout"],
                )
                divider_y = top - PAIR_BLOCK_H - GAP / 2
                canvas.setStrokeColor(DIVIDER)
                canvas.setLineWidth(0.55)
                canvas.line(MARGIN_X, divider_y, W - MARGIN_X, divider_y)
            elif sheet["kind"] == "single":
                item = sheet["items"][0]
                suffix = "  /  讲稿续下页" if item.get("continued") else ""
                draw_block(
                    canvas, pages[item["index"]], images[item["index"]],
                    top, SINGLE_BLOCK_H, item["layout"], item["text"], suffix,
                )
            else:
                page = pages[sheet["index"]]
                draw_continuation(
                    canvas, page, sheet["text"], sheet["number"], sheet["total"]
                )
            canvas.setFillColor(MUTED)
            canvas.setFont("CN", 6.5)
            canvas.drawRightString(W - MARGIN_X, 4.5 * mm, f"{sheet_number} / {len(plan)}")
            canvas.showPage()
        canvas.save()

    expected_sheets = len(plan)
    if len(PdfReader(str(args.output)).pages) != expected_sheets:
        raise RuntimeError("Output page count is incorrect.")
    if args.qa_dir:
        args.qa_dir.mkdir(parents=True, exist_ok=True)
        run(["pdftoppm", "-jpeg", "-r", "120", str(args.output), str(args.qa_dir / "page")])
    characters = len(mapping.get("cleaned_transcript", ""))
    paired_sheets = sum(item["kind"] == "pair" for item in plan)
    single_sheets = sum(item["kind"] == "single" for item in plan)
    continuation_sheets = sum(item["kind"] == "continuation" for item in plan)
    print(json.dumps({
        "output": str(args.output.resolve()),
        "slides": slide_count,
        "a4_pages": expected_sheets,
        "two_slide_pages": paired_sheets,
        "one_slide_pages": single_sheets,
        "continuation_pages": continuation_sheets,
        "minimum_pair_body_font_pt": PAIR_MIN_PT,
        "minimum_single_body_font_pt": SINGLE_MIN_PT,
        "layout_text_verified": True,
        "cleaned_transcript_characters": characters,
        "coverage": f"{characters}/{characters}",
    }, ensure_ascii=False))


if __name__ == "__main__":
    build(parse_args())
