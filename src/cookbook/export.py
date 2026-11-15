import io
import sqlite3
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import tomli_w
from PIL import Image as PillowImage
from pydantic import BaseModel, ConfigDict
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    Image,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from cookbook import queries
from cookbook.draft import DraftImages, IngredientLine, IngredientSection, RecipeDraft, Step
from cookbook.schema import TAG_KINDS
from cookbook.units import format_minutes

FONT_DIR = Path(__file__).parent / "fonts"
INK = HexColor("#000000")
GREY = HexColor("#6b6b6b")
HAIR = HexColor("#d4d4d4")
ACCENT = HexColor("#00703c")
PAGE_MARGIN = 15 * mm
COLUMN_GAP = 8 * mm
INGREDIENTS_SHARE = 0.34
HERO_MAX_HEIGHT = 70 * mm
HERO_PRINT_PIXELS = 1200
# Exported tags are grouped by kind, cuisine first, as hand-written drafts list them.
TAG_KIND_ORDER: list[str | None] = [*TAG_KINDS, None]


class ExportedNote(BaseModel):
    """A note as written to notes.toml; step is the step's position for a step note."""

    model_config = ConfigDict(frozen=True)

    body: str
    step: int | None
    step_title: str | None
    created_at: str
    updated_at: str


class RecipeExport(BaseModel):
    """A recipe as exported: its draft, the draft's image files by name, and its notes."""

    model_config = ConfigDict(frozen=True)

    draft: RecipeDraft
    images: dict[str, bytes]
    notes: list[ExportedNote]
    archived: bool


def recipe_export(connection: sqlite3.Connection, slug: str) -> RecipeExport | None:
    """
    Read a recipe back into the draft format recipe-db imports, with its images and notes.

    The draft's images block is written only when the recipe has both a hero and a card,
    as a draft requires; alt, credit and origin come from the hero.
    """
    row = connection.execute(
        """
        SELECT recipes.*, sources.publication, sources.author
        FROM recipes LEFT JOIN sources ON sources.id = recipes.source_id
        WHERE recipes.slug = ?
        """,
        (slug,),
    ).fetchone()
    if row is None:
        return None
    recipe_id = row["id"]

    images = {
        image["role"]: image
        for image in connection.execute(
            "SELECT role, data, alt, credit, origin FROM images WHERE recipe_id = ?",
            (recipe_id,),
        )
    }
    draft_images = None
    image_files: dict[str, bytes] = {}
    if "hero" in images and "card" in images:
        hero = images["hero"]
        draft_images = DraftImages(
            hero="hero.webp",
            card="card.webp",
            hero_alt=hero["alt"],
            credit=hero["credit"],
            origin=hero["origin"],
        )
        image_files = {"hero.webp": hero["data"], "card.webp": images["card"]["data"]}

    sections = []
    for section_id, name in connection.execute(
        "SELECT id, name FROM ingredient_sections WHERE recipe_id = ? ORDER BY position",
        (recipe_id,),
    ):
        lines = [
            IngredientLine(quantity=quantity, item=item, grams=grams)
            for quantity, item, grams in connection.execute(
                """
                SELECT quantity, item, grams_override FROM ingredients
                WHERE section_id = ? ORDER BY position
                """,
                (section_id,),
            )
        ]
        if lines:
            sections.append(IngredientSection(name=name, items=lines))

    draft = RecipeDraft(
        slug=row["slug"],
        title=row["title"],
        url=row["url"],
        archive_url=row["archive_url"],
        publication=row["publication"],
        author=row["author"] or None,
        serves=row["serves_text"],
        measure_system=row["measure_system"],
        prep_min=row["prep_min"],
        cook_min=row["cook_min"],
        rest_min=row["rest_min"],
        total_min=row["total_min"],
        intro=row["intro"],
        tags=[
            name
            for _, name in sorted(
                (TAG_KIND_ORDER.index(kind), name)
                for name, kind in connection.execute(
                    """
                    SELECT tags.name, tags.kind FROM recipe_tags
                    JOIN tags ON tags.id = recipe_tags.tag_id WHERE recipe_tags.recipe_id = ?
                    """,
                    (recipe_id,),
                )
            )
        ],
        steps=[
            Step(title=title, text=text)
            for title, text in connection.execute(
                "SELECT title, text FROM steps WHERE recipe_id = ? ORDER BY position",
                (recipe_id,),
            )
        ],
        images=draft_images,
        sections=sections,
    )
    notes = [
        ExportedNote.model_validate(dict(note))
        for note in connection.execute(
            """
            SELECT recipe_notes.body, steps.position AS step, steps.title AS step_title,
                   recipe_notes.created_at, recipe_notes.updated_at
            FROM recipe_notes LEFT JOIN steps ON steps.id = recipe_notes.step_id
            WHERE recipe_notes.recipe_id = ? ORDER BY recipe_notes.created_at, recipe_notes.id
            """,
            (recipe_id,),
        )
    ]
    return RecipeExport(
        draft=draft, images=image_files, notes=notes, archived=bool(row["archived"])
    )


def all_recipe_exports(connection: sqlite3.Connection) -> list[RecipeExport]:
    """Export every recipe, archived ones included, by slug."""
    exports = []
    for (slug,) in connection.execute("SELECT slug FROM recipes ORDER BY slug"):
        export = recipe_export(connection, slug)
        if export is not None:
            exports.append(export)
    return exports


def drafts_zip(exports: list[RecipeExport]) -> bytes:
    """
    Zip recipes as draft folders, one <slug>/ folder each, ready for recipe-db's import.

    Each folder holds recipe.toml, its images, and notes.toml when the recipe has notes;
    import reads only the draft and images. archived.txt lists the archived recipes'
    slugs, as the draft format has no field for it.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archived = [export.draft.slug for export in exports if export.archived]
        if archived:
            archive.writestr("archived.txt", "".join(f"{slug}\n" for slug in archived))
        for export in exports:
            folder = export.draft.slug
            archive.writestr(f"{folder}/recipe.toml", export.draft.to_toml())
            for name, data in export.images.items():
                archive.writestr(f"{folder}/{name}", data, compress_type=zipfile.ZIP_STORED)
            if export.notes:
                notes = [note.model_dump(exclude_none=True) for note in export.notes]
                archive.writestr(f"{folder}/notes.toml", tomli_w.dumps({"notes": notes}))
    return buffer.getvalue()


def hero_data(connection: sqlite3.Connection, slug: str) -> bytes | None:
    row = connection.execute(
        """
        SELECT images.data FROM images JOIN recipes ON recipes.id = images.recipe_id
        WHERE recipes.slug = ? AND images.role = 'hero'
        """,
        (slug,),
    ).fetchone()
    return row["data"] if row is not None else None


def register_fonts() -> None:
    """Register the bundled Inter files with ReportLab once per process."""
    if "Inter" in pdfmetrics.getRegisteredFontNames():
        return
    for name, file_name in [
        ("Inter", "Inter-Regular.ttf"),
        ("Inter-Bold", "Inter-Bold.ttf"),
        ("Inter-Italic", "Inter-Italic.ttf"),
    ]:
        pdfmetrics.registerFont(TTFont(name, FONT_DIR / file_name))
    pdfmetrics.registerFontFamily(
        "Inter", normal="Inter", bold="Inter-Bold", italic="Inter-Italic", boldItalic="Inter-Bold"
    )


def draw_footer(canvas: Canvas, document: BaseDocTemplate) -> None:
    canvas.saveState()
    canvas.setFont("Inter", 7)
    canvas.setFillColor(GREY)
    canvas.drawString(PAGE_MARGIN, PAGE_MARGIN / 2, document.title or "")
    canvas.drawRightString(A4[0] - PAGE_MARGIN, PAGE_MARGIN / 2, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def recipe_pdf(recipe: queries.Recipe, hero: bytes | None, include_notes: bool) -> bytes:
    """
    Lay a recipe out on A4 like the site: header and hero, then ingredients beside the method.

    The two columns are the two cells of one table row that may split across pages, so a
    long ingredient list and a long method each carry on in their own column.
    """
    register_fonts()
    body = ParagraphStyle("body", fontName="Inter", fontSize=9.5, leading=13, textColor=INK)
    label = ParagraphStyle("label", parent=body, fontName="Inter-Bold", fontSize=7, leading=9)
    styles = {
        "kicker": ParagraphStyle("kicker", parent=label, textColor=ACCENT, spaceAfter=6),
        "title": ParagraphStyle(
            "title", parent=body, fontName="Inter-Bold", fontSize=30, leading=31, spaceAfter=8
        ),
        "source": ParagraphStyle("source", parent=body, spaceAfter=6),
        "meta": ParagraphStyle("meta", parent=body, spaceAfter=4),
        "tags": ParagraphStyle("tags", parent=body, textColor=GREY, spaceAfter=8),
        "note": ParagraphStyle("note", parent=body, fontName="Inter-Italic", spaceBefore=3),
        "section": ParagraphStyle(
            "section", parent=label, textColor=ACCENT, spaceBefore=8, spaceAfter=2
        ),
        "column_head": ParagraphStyle("column_head", parent=label, spaceAfter=4),
        "step_title": ParagraphStyle(
            "step_title",
            parent=body,
            fontName="Inter-Bold",
            fontSize=11,
            leading=14,
            textColor=ACCENT,
        ),
    }

    page_width, page_height = A4
    frame_width = page_width - 2 * PAGE_MARGIN
    frame_height = page_height - 2 * PAGE_MARGIN

    header: list[Flowable] = [Paragraph(escape(recipe.kicker.upper()), styles["kicker"])]
    header.append(Paragraph(escape(recipe.title), styles["title"]))
    if recipe.source is not None or recipe.url:
        source_text = escape(
            " · ".join(
                part
                for part in [
                    recipe.source.publication if recipe.source else None,
                    recipe.source.author if recipe.source else None,
                ]
                if part
            )
            or "Source"
        )
        if recipe.url:
            url = escape(recipe.url, {'"': "&quot;"})
            source_text = f'<a href="{url}" color="#000000"><u>{source_text}</u></a>'
        header.append(Paragraph(source_text, styles["source"]))
    facts = [
        (name, format_minutes(minutes))
        for name, minutes in [
            ("PREP", recipe.prep_min),
            ("COOK", recipe.cook_min),
            ("REST", recipe.rest_min),
            ("TOTAL", recipe.total_min),
        ]
        if minutes
    ]
    if recipe.serves_text:
        facts.append(("MAKES" if recipe.yield_unit else "SERVES", recipe.serves_text))
    if facts:
        header.append(
            Paragraph(
                "&nbsp;&nbsp;&nbsp;&nbsp;".join(
                    f'<font name="Inter-Bold" size="7" color="#6b6b6b">{name}</font>'
                    f"&nbsp;<b>{escape(value)}</b>"
                    for name, value in facts
                ),
                styles["meta"],
            )
        )
    if recipe.tags:
        tags = "&nbsp;&nbsp;".join(
            f'<font color="#00703c">#</font>{escape(tag.name)}' for tag in recipe.tags
        )
        header.append(Paragraph(tags, styles["tags"]))
    if hero is not None:
        # ReportLab would store a WebP as raw pixels, megabytes per page; a JPEG it embeds
        # as is. 1200 px across the 180 mm frame is about 170 dpi, plenty for a printout.
        photo = PillowImage.open(io.BytesIO(hero)).convert("RGB")
        photo.thumbnail((HERO_PRINT_PIXELS, HERO_PRINT_PIXELS))
        jpeg = io.BytesIO()
        photo.save(jpeg, "JPEG", quality=82)
        width, height = photo.size
        scale = min(frame_width / width, HERO_MAX_HEIGHT / height)
        picture = Image(jpeg, width=width * scale, height=height * scale)
        picture.hAlign = "LEFT"
        header.append(picture)
        if recipe.hero is not None and recipe.hero.credit:
            credit_style = ParagraphStyle("credit", parent=body, fontSize=7, textColor=GREY)
            header.append(Paragraph(escape(recipe.hero.credit), credit_style))
    if recipe.intro:
        header.append(Paragraph(escape(recipe.intro), styles["source"]))
    if include_notes:
        header.extend(Paragraph(escape(note.body), styles["note"]) for note in recipe.notes)
    header.append(Spacer(1, 6 * mm))

    ingredients_width = frame_width * INGREDIENTS_SHARE
    method_width = frame_width - ingredients_width - COLUMN_GAP

    ingredients: list[Flowable] = [Paragraph("INGREDIENTS", styles["column_head"])]
    for section in recipe.sections:
        if section.name:
            ingredients.append(Paragraph(escape(section.name.upper()), styles["section"]))
        rows = [
            [
                Paragraph(f"<b>{escape(line.quantity)}</b>", body),
                Paragraph(escape("".join(piece.text for piece in line.item_pieces)), body),
            ]
            for line in section.ingredients
        ]
        table = Table(rows, colWidths=[ingredients_width * 0.36, ingredients_width * 0.64])
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (0, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, HAIR),
                ]
            )
        )
        ingredients.append(table)

    method: list[Flowable] = [Paragraph("METHOD", styles["column_head"])]
    for number, step in enumerate(recipe.steps, start=1):
        block: list[Flowable] = [
            Paragraph(
                f'<font color="#6b6b6b">{number:02d}</font>&nbsp;&nbsp;{escape(step.title)}',
                styles["step_title"],
            ),
            Paragraph(escape("".join(piece.text for piece in step.text_pieces)), body),
        ]
        if include_notes:
            block.extend(Paragraph(escape(note.body), styles["note"]) for note in step.notes)
        # A one-cell table, not KeepTogether, which fails inside a splitting cell: a table
        # row that doesn't fit moves to the next page whole, keeping the step together.
        step_table = Table([[block]], colWidths=[method_width])
        step_table.setStyle(
            TableStyle(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0 if number == 1 else 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        method.append(step_table)

    columns = Table(
        [[ingredients, method]],
        colWidths=[ingredients_width + COLUMN_GAP, method_width],
        splitInRow=1,
    )
    columns.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), COLUMN_GAP),
                ("RIGHTPADDING", (1, 0), (1, 0), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    buffer = io.BytesIO()
    document = BaseDocTemplate(
        buffer,
        pagesize=A4,
        pageTemplates=[
            PageTemplate(
                frames=[Frame(PAGE_MARGIN, PAGE_MARGIN, frame_width, frame_height, 0, 0, 0, 0)],
                onPage=draw_footer,
            )
        ],
        title=recipe.title,
        author="Cookbook",
    )
    document.build([*header, columns])
    return buffer.getvalue()
