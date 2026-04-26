from pathlib import Path
from datetime import datetime, timezone
from scholarly import scholarly
import yaml
import html

SCHOLAR_ID = "xqccd64AAAAJ"

OUT = Path("_pages/publication.md")
NOTES_FILE = Path("_data/publication_notes.yml")


def clean_text(value):
    if not value:
        return ""
    return str(value).replace("\n", " ").strip()


def load_notes():
    if not NOTES_FILE.exists():
        return {}

    with NOTES_FILE.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def safe_html(value):
    return html.escape(str(value), quote=False)


def add_field(lines, label, value):
    if not value:
        return

    value = str(value).strip()

    if value.startswith("http"):
        lines.append(
            f'<strong>{label}:</strong> '
            f'<a href="{value}" target="new">Link</a> <br>'
        )
    else:
        lines.append(f"<strong>{label}:</strong> {safe_html(value)} <br>")


def get_year(pub):
    year = pub.get("year", "")
    if str(year).isdigit():
        return int(year)
    return 0


def fetch_scholar_data():
    print("Fetching Google Scholar profile...")

    author = scholarly.search_author_id(SCHOLAR_ID)

    print("Fetching citation metrics and publication list...")

    author = scholarly.fill(
        author,
        sections=["basics", "indices", "publications"],
        publication_limit=150,
    )

    citedby = author.get("citedby", "")
    hindex = author.get("hindex", "")
    i10index = author.get("i10index", "")

    publications = []

    for pub in author.get("publications", []):
        bib = pub.get("bib", {})

        title = clean_text(bib.get("title"))
        if not title:
            continue

        publications.append(
            {
                "title": title,
                "authors": clean_text(bib.get("author")),
                "venue": clean_text(
                    bib.get("journal")
                    or bib.get("conference")
                    or bib.get("venue")
                    or bib.get("publisher")
                ),
                "year": clean_text(bib.get("pub_year")),
            }
        )

    publications.sort(key=get_year, reverse=True)

    return {
        "citedby": citedby,
        "hindex": hindex,
        "i10index": i10index,
        "publications": publications,
    }


def build_page(data, notes):
    last_updated = datetime.now(timezone.utc).strftime("%B %d, %Y, %H:%M UTC")

    citedby = data.get("citedby", "")
    hindex = data.get("hindex", "")
    i10index = data.get("i10index", "")
    publications = data.get("publications", [])

    lines = [
        "---",
        "title: Publications",
        "layout: archive",
        "classes: wide",
        "permalink: /publication/",
        "author_profile: true",
        "excerpt: This page shows a list of Javad Pourmostafa's papers and talks.",
        "---",
        "",
        "I have published under the name **Javad Pourmostafa Roshan Sharami**, where *Roshan Sharami* is a suffix added to my last name.",
        "",
        f"<p style='font-size: 80%; color: gray;'><em>Last updated: {last_updated}</em></p>",
        "",
        "## Citation Metrics",
        "",
        '<p style="font-size: 90%;">',
    ]

    if citedby:
        lines.append(f"<strong>Total citations:</strong> {citedby} <br>")
    if hindex:
        lines.append(f"<strong>h-index:</strong> {hindex} <br>")
    if i10index:
        lines.append(f"<strong>i10-index:</strong> {i10index} <br>")

    lines.extend(
        [
            "</p>",
            "",
            '<hr style="border: 1px solid #ddd; margin: 2em 0;" />',
            "",
            "<!-- This page is automatically generated. -->",
            "<!-- Add optional manual details in _data/publication_notes.yml. -->",
            "",
        ]
    )

    current_year = None

    for pub in publications:
        title = pub["title"]
        extra = notes.get(title, {}) or {}

        year = extra.get("year") or pub.get("year", "")

        if year and year != current_year:
            lines.append(f"# {year}")
            lines.append("")
            current_year = year

        authors = extra.get("authors") or pub.get("authors", "")
        venue = extra.get("venue") or pub.get("venue", "")

        lines.append(f"## {safe_html(title)}")
        lines.append("")
        lines.append('<p style="font-size: 90%;">')

        add_field(lines, "Authors", authors)
        add_field(lines, "Venue", venue)
        add_field(lines, "Year", year)

        optional_fields = [
            ("date", "Date"),
            ("status", "Status"),
            ("proceedings", "Proceedings"),
            ("series", "Series"),
            ("pages", "Pages"),
            ("doi", "DOI"),
            ("arxiv", "arXiv"),
            ("pdf", "PDF"),
            ("paper", "Paper"),
            ("preprint", "Preprint"),
            ("code", "Code / Tool"),
            ("slides", "Slides"),
            ("video", "Video"),
            ("talk", "Talk"),
            ("certificate", "Certificate"),
            ("resources", "Resources"),
            ("note", "Note"),
        ]

        for key, label in optional_fields:
            add_field(lines, label, extra.get(key))

        lines.append("</p>")
        lines.append("")
        lines.append('<hr style="border: 1px solid #ddd; margin: 2em 0;" />')
        lines.append("")

    return "\n".join(lines)


def main():
    notes = load_notes()

    try:
        data = fetch_scholar_data()
    except Exception as e:
        print("Could not fetch from Google Scholar.")
        print(e)
        print("Existing publication page will stay unchanged.")
        return

    page = build_page(data, notes)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")

    print(f"Updated {OUT}")
    print(f"Number of publications: {len(data.get('publications', []))}")
    print(f"Citations: {data.get('citedby', '')}")
    print(f"h-index: {data.get('hindex', '')}")
    print(f"i10-index: {data.get('i10index', '')}")


if __name__ == "__main__":
    main()
