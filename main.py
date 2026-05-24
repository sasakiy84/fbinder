"""Markdown / CSV / static files are converted into a static HTML site.

Usage:
    uv run python main.py build --source ./content --output ./public
    uv run python main.py check --source ./content
    uv run python main.py watch --source ./content --output ./public
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import logging
import posixpath
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from string import Template
from typing import Literal, Sequence, TypedDict
from urllib.parse import quote

from markdown_it import MarkdownIt
from markdown_it.token import Token


ItemKind = Literal["markdown", "csv", "file", "index"]


@dataclass(frozen=True)
class BuildError:
    source_rel: PurePosixPath
    operation: str
    error_type: str
    message: str
    line: int | None = None


class RecoverableBuildError(Exception):
    def __init__(self, error: BuildError) -> None:
        self.error = error
        super().__init__(error.message)


@dataclass(frozen=True)
class SiteItem:
    source_rel: PurePosixPath
    output_rel: PurePosixPath
    title: str
    kind: ItemKind
    mtime: float
    favorite: bool = False


@dataclass(frozen=True)
class TocItem:
    level: int
    title: str
    anchor: str


@dataclass(frozen=True)
class RenderedPage:
    output_rel: PurePosixPath
    title: str
    body_html: str
    source_rel: PurePosixPath
    kind: ItemKind
    mtime: float
    toc_items: list[TocItem]
    copy_markdown: str | None
    search_text: str
    favorite: bool = False


@dataclass(frozen=True)
class BuildResult:
    output_dir: Path
    errors: list[BuildError]
    pages: list[RenderedPage]
    files: list[SiteItem]


class FatalBuildError(Exception):
    """Raised when a site build cannot safely start or complete."""


class SearchIndexEntry(TypedDict):
    title: str
    url: str
    kind: ItemKind
    updated: str
    text: str


class SearchIndexDocument(TypedDict):
    version: int
    items: list[SearchIndexEntry]


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if args.command == "build":
        return build_command(args.source, args.output)
    if args.command == "check":
        return check_command(args.source, args.output)
    if args.command == "watch":
        return watch_command(args.source, args.output, args.interval)

    parser.print_help()
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fbinder")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Generate a static HTML site.")
    build.add_argument("--source", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)

    check = subparsers.add_parser("check", help="Validate input files.")
    check.add_argument("--source", required=True, type=Path)
    check.add_argument("--output", type=Path)

    watch = subparsers.add_parser("watch", help="Rebuild when source files change.")
    watch.add_argument("--source", required=True, type=Path)
    watch.add_argument("--output", required=True, type=Path)
    watch.add_argument("--interval", type=float, default=1.0)

    return parser


def build_command(source: Path, output: Path) -> int:
    try:
        result = build_site(source, output)
    except FatalBuildError as exc:
        logging.error("%s", exc)
        return 1

    if result.errors:
        logging.warning("built with %d recoverable error(s)", len(result.errors))
    else:
        logging.info("built %s", result.output_dir)
    return 0


def check_command(source: Path, output: Path | None) -> int:
    try:
        errors = check_source(source, output)
    except FatalBuildError as exc:
        logging.error("%s", exc)
        return 1

    if not errors:
        logging.info("check passed")
        return 0

    for error in errors:
        line = f":{error.line}" if error.line is not None else ""
        logging.error(
            "%s%s [%s] %s",
            error.source_rel.as_posix(),
            line,
            error.operation,
            error.message,
        )
    return 1


def watch_command(source: Path, output: Path, interval: float) -> int:
    try:
        from watchfiles import watch
    except ImportError as exc:
        logging.error("watch requires watchfiles: %s", exc)
        return 1

    exit_code = build_command(source, output)
    if exit_code != 0:
        return exit_code

    logging.info("watching %s", source)
    for changes in watch(source):
        changed_paths = ", ".join(sorted(str(change[1]) for change in changes))
        logging.info("change detected: %s", changed_paths)
        time.sleep(interval)
        build_command(source, output)

    return 0


def build_site(source: Path, output: Path) -> BuildResult:
    source_dir = validate_source_dir(source)
    output_dir = output.resolve()
    ensure_output_is_not_inside_source(source_dir, output_dir)

    temp_dir = output_dir.with_name(f"{output_dir.name}.tmp")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    try:
        errors: list[BuildError] = []
        pages, files = collect_site(source_dir, errors)
        write_static_assets(temp_dir)
        copied_files = copy_static_files(source_dir, temp_dir, files, errors)
        page_map = {page.output_rel: page for page in pages}
        index_pages = build_index_pages(source_dir, pages, copied_files)
        write_search_index(temp_dir, pages)

        for index_page in index_pages:
            page_map[index_page.output_rel] = merge_index_page(
                page_map.get(index_page.output_rel),
                index_page,
            )

        generated_at = datetime.now()
        rendered_pages = sorted(page_map.values(), key=lambda page: page.output_rel.as_posix())
        if errors:
            rendered_pages.append(build_errors_page(errors))

        for page in rendered_pages:
            html_text = render_document(page, bool(errors), generated_at)
            write_text_file(temp_dir / Path(*page.output_rel.parts), html_text)

        replace_output_dir(output_dir, temp_dir)
        return BuildResult(output_dir=output_dir, errors=errors, pages=rendered_pages, files=copied_files)
    except Exception as exc:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        if isinstance(exc, FatalBuildError):
            raise
        raise FatalBuildError(f"build failed before output update: {exc}") from exc


def check_source(source: Path, output: Path | None) -> list[BuildError]:
    source_dir = validate_source_dir(source)
    if output is not None:
        ensure_output_is_not_inside_source(source_dir, output.resolve())

    errors: list[BuildError] = []
    collect_site(source_dir, errors)
    return errors


def validate_source_dir(source: Path) -> Path:
    source_dir = source.resolve()
    if not source_dir.exists():
        raise FatalBuildError(f"source directory does not exist: {source}")
    if not source_dir.is_dir():
        raise FatalBuildError(f"source is not a directory: {source}")
    return source_dir


def ensure_output_is_not_inside_source(source_dir: Path, output_dir: Path) -> None:
    if output_dir == source_dir or output_dir.is_relative_to(source_dir):
        raise FatalBuildError("output directory must not be inside source directory")


def collect_site(source_dir: Path, errors: list[BuildError]) -> tuple[list[RenderedPage], list[SiteItem]]:
    pages: list[RenderedPage] = []
    files: list[SiteItem] = []
    outputs: dict[PurePosixPath, PurePosixPath] = {}

    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue

        source_rel = to_posix_path(path.relative_to(source_dir))
        try:
            page = render_source_file(source_dir, source_rel)
        except RecoverableBuildError as exc:
            errors.append(exc.error)
            continue

        output_rel = page.output_rel if isinstance(page, RenderedPage) else page.output_rel
        conflict = outputs.get(output_rel)
        if conflict is not None:
            errors.append(
                BuildError(
                    source_rel=source_rel,
                    operation="output path",
                    error_type="Collision",
                    message=f"output path conflicts with {conflict.as_posix()}",
                )
            )
            continue

        if is_reserved_output_path(source_rel, output_rel):
            errors.append(
                BuildError(
                    source_rel=source_rel,
                    operation="output path",
                    error_type="ReservedPath",
                    message=f"{output_rel.as_posix()} is reserved for generated site files",
                )
            )
            continue

        outputs[output_rel] = source_rel
        if isinstance(page, RenderedPage):
            pages.append(page)
        else:
            files.append(page)

    return pages, files


def render_source_file(source_dir: Path, source_rel: PurePosixPath) -> RenderedPage | SiteItem:
    source_path = source_dir / Path(*source_rel.parts)
    suffix = source_rel.suffix.lower()
    if suffix == ".md":
        return render_markdown_file(source_path, source_rel)
    if suffix == ".csv":
        return render_csv_file(source_path, source_rel)

    return SiteItem(
        source_rel=source_rel,
        output_rel=source_rel,
        title=display_name(source_rel),
        kind="file",
        mtime=source_path.stat().st_mtime,
    )


def render_markdown_file(source_path: Path, source_rel: PurePosixPath) -> RenderedPage:
    try:
        raw_text = source_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise RecoverableBuildError(
            BuildError(
                source_rel=source_rel,
                operation="Markdown conversion",
                error_type=type(exc).__name__,
                message=str(exc),
            )
        ) from exc

    front_matter, markdown_text = parse_front_matter(raw_text)
    title = front_matter.get("title")
    if not isinstance(title, str) or not title.strip():
        title = extract_first_h1(markdown_text) or display_name(source_rel)
    favorite = front_matter_flag_enabled(front_matter, "favorite")

    output_rel = source_rel.with_suffix(".html")
    body_html, toc_items = render_markdown_body(markdown_text)
    return RenderedPage(
        output_rel=output_rel,
        title=title.strip(),
        body_html=body_html,
        source_rel=source_rel,
        kind="markdown",
        mtime=source_path.stat().st_mtime,
        toc_items=toc_items,
        copy_markdown=markdown_text,
        search_text=join_search_text([title.strip(), front_matter_search_text(front_matter), markdown_text]),
        favorite=favorite,
    )


def parse_front_matter(raw_text: str) -> tuple[dict[str, str | list[str]], str]:
    lines = raw_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, raw_text

    closing_index: int | None = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing_index = index
            break

    if closing_index is None:
        return {}, raw_text

    metadata: dict[str, str | list[str]] = {}
    for line in lines[1:closing_index]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value.startswith("[") and value.endswith("]"):
            items: list[str] = []
            for item in value[1:-1].split(","):
                cleaned = item.strip().strip("\"'")
                if cleaned:
                    items.append(cleaned)
            metadata[key] = items
        else:
            metadata[key] = value.strip("\"'")

    body = "\n".join(lines[closing_index + 1 :])
    if raw_text.endswith("\n"):
        body += "\n"
    return metadata, body


def extract_first_h1(markdown_text: str) -> str | None:
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("# ") or stripped.startswith("## "):
            continue
        title = stripped[2:].strip()
        while title.endswith("#"):
            title = title[:-1].strip()
        if title:
            return title
    return None


def render_markdown_body(markdown_text: str) -> tuple[str, list[TocItem]]:
    markdown = MarkdownIt("commonmark", {"html": False})
    tokens: list[Token] = markdown.parse(markdown_text)
    toc_items: list[TocItem] = []

    for index, token in enumerate(tokens):
        if token.tag == "h1":
            token.tag = "h2"
            token.markup = "##"
        if token.type != "heading_open" or token.tag not in {"h2", "h3", "h4", "h5", "h6"}:
            continue
        if index + 1 >= len(tokens):
            continue

        inline = tokens[index + 1]
        if inline.type != "inline" or not inline.content.strip():
            continue

        anchor = f"heading-{len(toc_items) + 1}"
        token.attrSet("id", anchor)
        toc_items.append(TocItem(level=int(token.tag[1]), title=inline.content.strip(), anchor=anchor))

    rendered = markdown.renderer.render(tokens, markdown.options, {})
    return rendered.replace("<pre><code", '<pre tabindex="0"><code'), toc_items


def render_csv_file(source_path: Path, source_rel: PurePosixPath) -> RenderedPage:
    try:
        with source_path.open("r", encoding="utf-8", newline="") as csv_file:
            rows = list(csv.reader(csv_file))
    except UnicodeDecodeError as exc:
        raise RecoverableBuildError(
            BuildError(
                source_rel=source_rel,
                operation="CSV conversion",
                error_type=type(exc).__name__,
                message=str(exc),
            )
        ) from exc
    except csv.Error as exc:
        raise RecoverableBuildError(
            BuildError(
                source_rel=source_rel,
                operation="CSV conversion",
                error_type=type(exc).__name__,
                message=str(exc),
            )
        ) from exc

    if not rows or all(not cell.strip() for cell in rows[0]):
        raise RecoverableBuildError(
            BuildError(
                source_rel=source_rel,
                operation="CSV conversion",
                error_type="EmptyHeader",
                message="CSV header is empty",
                line=1,
            )
        )

    header = rows[0]
    for line_number, row in enumerate(rows[1:], start=2):
        if len(row) != len(header):
            raise RecoverableBuildError(
                BuildError(
                    source_rel=source_rel,
                    operation="CSV conversion",
                    error_type="ColumnCountMismatch",
                    message=f"expected {len(header)} columns but found {len(row)}",
                    line=line_number,
                )
            )

    title = display_name(source_rel)
    output_rel = source_rel.with_suffix(".html")
    body_html = render_csv_table(title, header, rows[1:])
    copy_markdown = render_csv_markdown_table(header, rows[1:])
    return RenderedPage(
        output_rel=output_rel,
        title=title,
        body_html=body_html,
        source_rel=source_rel,
        kind="csv",
        mtime=source_path.stat().st_mtime,
        toc_items=[],
        copy_markdown=copy_markdown,
        search_text=csv_search_text(title, header, rows[1:]),
    )


def front_matter_search_text(front_matter: dict[str, str | list[str]]) -> str:
    values: list[str] = []
    for key, value in front_matter.items():
        if key == "favorite":
            continue
        if isinstance(value, str):
            values.append(value)
        else:
            values.extend(value)
    return join_search_text(values)


def front_matter_flag_enabled(front_matter: dict[str, str | list[str]], key: str) -> bool:
    value = front_matter.get(key)
    if not isinstance(value, str):
        return False
    return value.strip().casefold() in {"true", "yes", "1", "on"}


def csv_search_text(title: str, header: list[str], rows: list[list[str]]) -> str:
    values: list[str] = [title]
    values.extend(header)
    for row in rows:
        values.extend(row)
    return join_search_text(values)


def join_search_text(values: Sequence[str]) -> str:
    parts: list[str] = []
    for value in values:
        cleaned = " ".join(value.split())
        if cleaned:
            parts.append(cleaned)
    return " ".join(parts)


def render_csv_table(title: str, header: list[str], rows: list[list[str]]) -> str:
    header_cells = "".join(f'<th scope="col">{html.escape(cell)}</th>' for cell in header)
    row_html: list[str] = []
    for row in rows:
        cells = "".join(f"<td>{render_csv_cell(cell)}</td>" for cell in row)
        row_html.append(f"<tr>{cells}</tr>")

    body = "\n".join(row_html)
    return (
        '<div class="table-wrap">\n'
        "<table>\n"
        f"<caption>{html.escape(title)}</caption>\n"
        f"<thead><tr>{header_cells}</tr></thead>\n"
        f"<tbody>\n{body}\n</tbody>\n"
        "</table>\n"
        "</div>"
    )


def render_csv_cell(value: str) -> str:
    stripped = value.strip()
    escaped = html.escape(value)
    if stripped.startswith("http://") or stripped.startswith("https://"):
        href = html.escape(stripped, quote=True)
        return f'<a href="{href}">{escaped}</a>'
    return escaped


def render_csv_markdown_table(header: list[str], rows: list[list[str]]) -> str:
    header_line = "| " + " | ".join(escape_markdown_table_cell(cell) for cell in header) + " |"
    divider_line = "| " + " | ".join("---" for _ in header) + " |"
    body_lines: list[str] = []
    for row in rows:
        body_lines.append("| " + " | ".join(escape_markdown_table_cell(cell) for cell in row) + " |")
    return "\n".join([header_line, divider_line, *body_lines])


def escape_markdown_table_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def copy_static_files(
    source_dir: Path,
    output_dir: Path,
    files: list[SiteItem],
    errors: list[BuildError],
) -> list[SiteItem]:
    copied_files: list[SiteItem] = []
    for item in files:
        source_path = source_dir / Path(*item.source_rel.parts)
        output_path = output_dir / Path(*item.output_rel.parts)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, output_path)
            copied_files.append(item)
        except OSError as exc:
            errors.append(
                BuildError(
                    source_rel=item.source_rel,
                    operation="static file copy",
                    error_type=type(exc).__name__,
                    message=str(exc),
                )
            )
    return copied_files


def build_index_pages(
    source_dir: Path,
    pages: list[RenderedPage],
    files: list[SiteItem],
) -> list[RenderedPage]:
    directories: set[PurePosixPath] = {PurePosixPath(".")}
    for path in source_dir.rglob("*"):
        if path.is_dir():
            directories.add(to_posix_path(path.relative_to(source_dir)))

    items: list[SiteItem] = [
        SiteItem(page.source_rel, page.output_rel, page.title, page.kind, page.mtime, page.favorite)
        for page in pages
    ]
    items.extend(files)

    index_pages: list[RenderedPage] = []
    for directory in sorted(directories, key=lambda value: value.as_posix()):
        directory_items = [
            item for item in items if item.source_rel.parent == directory and item.source_rel.name != "index.md"
        ]
        child_dirs = sorted(
            child for child in directories if child.parent == directory and child != directory
        )
        title = "fbinder" if directory == PurePosixPath(".") else display_name(directory)
        output_rel = directory / "index.html" if directory != PurePosixPath(".") else PurePosixPath("index.html")
        body_html = render_index_body(title, output_rel, child_dirs, directory_items)
        index_pages.append(
            RenderedPage(
                output_rel=output_rel,
                title=title,
                body_html=body_html,
                source_rel=directory,
                kind="index",
                mtime=time.time(),
                toc_items=[],
                copy_markdown=None,
                search_text="",
            )
        )

    return index_pages


def merge_index_page(existing: RenderedPage | None, generated: RenderedPage) -> RenderedPage:
    if existing is None:
        return generated

    return RenderedPage(
        output_rel=existing.output_rel,
        title=existing.title,
        body_html=f"{existing.body_html}\n<section class=\"index-list\">\n{generated.body_html}\n</section>",
        source_rel=existing.source_rel,
        kind=existing.kind,
        mtime=existing.mtime,
        toc_items=existing.toc_items,
        copy_markdown=existing.copy_markdown,
        search_text=existing.search_text,
        favorite=existing.favorite,
    )


def render_index_body(
    title: str,
    current_output_rel: PurePosixPath,
    child_dirs: list[PurePosixPath],
    items: list[SiteItem],
) -> str:
    parts: list[str] = []

    if child_dirs:
        parts.append("<h2>Directories</h2>")
        parts.append("<ul>")
        for child_dir in child_dirs:
            index_rel = child_dir / "index.html"
            href = relative_url(current_output_rel, index_rel)
            parts.append(f'<li><a href="{href}">{html.escape(display_name(child_dir))}</a></li>')
        parts.append("</ul>")

    if items:
        parts.append("<h2>Files</h2>")
        parts.append("<ul class=\"file-list\">")
        for item in sorted(items, key=lambda value: (not value.favorite, value.source_rel.as_posix())):
            href = relative_url(current_output_rel, item.output_rel)
            label = html.escape(item.title)
            updated = html.escape(format_mtime(item.mtime))
            favorite_html = (
                '<span class="favorite-marker" aria-label="お気に入り" title="お気に入り">★</span> '
                if item.favorite
                else ""
            )
            parts.append(
                f'<li>{favorite_html}<a href="{href}">{label}</a> '
                f'<span class="meta">{updated}</span></li>'
            )
        parts.append("</ul>")

    if not parts:
        parts.append("<p>No files found.</p>")

    return "\n".join(parts)


def build_errors_page(errors: list[BuildError]) -> RenderedPage:
    rows: list[str] = []
    for error in errors:
        line = "" if error.line is None else str(error.line)
        rows.append(
            "<tr>"
            f"<td>{html.escape(error.source_rel.as_posix())}</td>"
            f"<td>{html.escape(line)}</td>"
            f"<td>{html.escape(error.operation)}</td>"
            f"<td>{html.escape(error.error_type)}</td>"
            f"<td>{html.escape(error.message)}</td>"
            "</tr>"
        )

    body_html = (
        '<div class="notice error">Recoverable errors occurred during generation.</div>\n'
        '<div class="table-wrap">\n'
        "<table>\n"
        "<caption>Build errors</caption>\n"
        "<thead><tr>"
        '<th scope="col">File</th>'
        '<th scope="col">Line</th>'
        '<th scope="col">Operation</th>'
        '<th scope="col">Type</th>'
        '<th scope="col">Message</th>'
        "</tr></thead>\n"
        f"<tbody>\n{''.join(rows)}\n</tbody>\n"
        "</table>\n"
        "</div>"
    )
    return RenderedPage(
        output_rel=PurePosixPath("errors.html"),
        title="Build errors",
        body_html=body_html,
        source_rel=PurePosixPath("errors.html"),
        kind="index",
        mtime=time.time(),
        toc_items=[],
        copy_markdown=None,
        search_text="",
    )


def render_document(
    page: RenderedPage,
    has_errors: bool,
    generated_at: datetime,
) -> str:
    current_output_rel = page.output_rel
    home_href = relative_url(current_output_rel, PurePosixPath("index.html"))
    style_href = relative_url(current_output_rel, PurePosixPath("static/style.css"))
    script_href = relative_url(current_output_rel, PurePosixPath("static/script.js"))
    search_index_href = relative_url(current_output_rel, PurePosixPath("search-index.json"))
    error_link_html = ""
    if has_errors:
        errors_href = relative_url(current_output_rel, PurePosixPath("errors.html"))
        error_link_html = f'<li><a href="{errors_href}">Errors</a></li>'

    template_path = project_path("templates", "page.html")
    template = Template(template_path.read_text(encoding="utf-8"))
    return template.substitute(
        page_title=html.escape(page.title),
        document_title=html.escape(f"{page.title} | fbinder"),
        style_href=style_href,
        script_href=script_href,
        search_index_href=search_index_href,
        home_href=home_href,
        error_link_html=error_link_html,
        page_meta_html=render_page_meta(page, generated_at),
        body_html=page.body_html,
    )


def render_page_meta(page: RenderedPage, generated_at: datetime) -> str:
    if page.kind not in {"markdown", "csv"} or page.output_rel.name == "index.html":
        return ""

    generated_iso = html.escape(generated_at.isoformat(timespec="seconds"))
    generated_text = html.escape(generated_at.strftime("%Y-%m-%d %H:%M"))
    parts: list[str] = [
        '<div class="page-tools">',
        '<p class="page-meta">生成日: '
        f'<time datetime="{generated_iso}">{generated_text}</time></p>',
        '<button type="button" class="copy-button" data-copy-content="copy-source" '
        'data-copy-label="Markdownをコピー" data-copy-empty-message="コピーするMarkdownがありません" '
        'data-copy-success-message="Markdownをコピーしました" aria-describedby="copy-status">'
        "Markdownをコピー</button>",
        '<button type="button" class="copy-button" data-copy-content="copy-source-path" '
        'data-copy-label="パスをコピー" data-copy-empty-message="コピーするパスがありません" '
        'data-copy-success-message="元ファイルの相対パスをコピーしました" aria-describedby="copy-status">'
        "パスをコピー</button>",
        '<span id="copy-status" class="copy-status" aria-live="polite"></span>',
        "</div>",
        '<textarea id="copy-source-path" class="copy-source" hidden readonly>'
        f"{html.escape(page.source_rel.as_posix(), quote=False)}"
        "</textarea>",
    ]
    if page.favorite:
        parts.insert(1, '<span class="favorite-label" aria-label="お気に入り">★ お気に入り</span>')
    if page.copy_markdown is not None:
        parts.append(
            '<textarea id="copy-source" class="copy-source" hidden readonly>'
            f"{html.escape(page.copy_markdown, quote=False)}"
            "</textarea>"
        )

    if page.toc_items:
        parts.append('<nav class="toc" aria-labelledby="toc-title">')
        parts.append('<h2 id="toc-title">目次</h2>')
        parts.append("<ol>")
        for item in page.toc_items:
            level_class = f"toc-level-{item.level}"
            parts.append(
                f'<li class="{level_class}"><a href="#{html.escape(item.anchor)}">'
                f"{html.escape(item.title)}</a></li>"
            )
        parts.append("</ol>")
        parts.append("</nav>")

    return "\n".join(parts)


def write_static_assets(output_dir: Path) -> None:
    static_dir = output_dir / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(project_path("static", "style.css"), static_dir / "style.css")
    shutil.copy2(project_path("static", "script.js"), static_dir / "script.js")


def write_search_index(output_dir: Path, pages: list[RenderedPage]) -> None:
    entries: list[SearchIndexEntry] = []
    for page in sorted(pages, key=lambda value: value.output_rel.as_posix()):
        if page.kind not in {"markdown", "csv"}:
            continue
        entries.append(
            SearchIndexEntry(
                title=page.title,
                url=quote_posix_path(page.output_rel),
                kind=page.kind,
                updated=format_mtime(page.mtime),
                text=page.search_text,
            )
        )

    document: SearchIndexDocument = {"version": 1, "items": entries}
    write_text_file(
        output_dir / "search-index.json",
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
    )


def write_text_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def project_path(*parts: str) -> Path:
    return Path(__file__).resolve().parent.joinpath(*parts)


def replace_output_dir(output_dir: Path, temp_dir: Path) -> None:
    backup_dir = output_dir.with_name(f"{output_dir.name}.old")
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    if output_dir.exists():
        output_dir.rename(backup_dir)
    temp_dir.rename(output_dir)
    if backup_dir.exists():
        shutil.rmtree(backup_dir)


def is_reserved_output_path(source_rel: PurePosixPath, output_rel: PurePosixPath) -> bool:
    if output_rel in {
        PurePosixPath("errors.html"),
        PurePosixPath("search-index.json"),
        PurePosixPath("static/style.css"),
        PurePosixPath("static/script.js"),
    }:
        return True
    return output_rel.name == "index.html" and source_rel.name != "index.md"


def display_name(path: PurePosixPath) -> str:
    name = path.stem if path.suffix else path.name
    return name.replace("_", " ").replace("-", " ").strip() or path.as_posix()


def format_mtime(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def relative_url(current_output_rel: PurePosixPath, target_output_rel: PurePosixPath) -> str:
    current_dir = current_output_rel.parent.as_posix()
    if current_dir == ".":
        current_dir = ""
    relative = posixpath.relpath(target_output_rel.as_posix(), start=current_dir or ".")
    if relative == ".":
        relative = target_output_rel.name
    return quote_posix_path(PurePosixPath(relative))


def quote_posix_path(path: PurePosixPath) -> str:
    return "/".join(quote(part) for part in path.parts)


def to_posix_path(path: Path) -> PurePosixPath:
    return PurePosixPath(path.as_posix())


if __name__ == "__main__":
    sys.exit(main())
