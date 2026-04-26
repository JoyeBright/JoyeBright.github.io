from pathlib import Path
from scholarly import scholarly
import yaml

SCHOLAR_ID = "xqccd64AAAAJ"

OUT = Path("_pages/publication.md")
NOTES_FILE = Path("_data/publication_notes.yml")


def clean_text(value):
    if not value:
        return ""
    return str(value).replace("\n", " ").strip()


def load_notes():
    if NOTES_FILE.exists():
        with NOTES_FILE.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def add_link_or_text(lines, label, value):
    if not value:
        return

    value = str(value).strip()

    if value.startswith("http"):
        lines.append(
            f'<strong>{label}:</strong> <a href="{value}" target="new">Link</a> <br>'
        )
    else:
        lines.append(f"<strong>{label}:</strong> {value} <br>")


def main():
    notes = load_notes()

    try:
        print("Fetching Google Scholar profile...")
        author = scholarly.search_author_id(SCHOLAR_ID)

        print("Fetching publication list...")
        author = scholarly.fill(author, sections=["publications"])

    except Exception as e:
        print("Could not fetch from Google Scholar.")
        print(e)
        print("Keeping existing publication.md unchanged.")
        return

    publications = []

    for pub in author.get("publications", []):
        bib = pub.get("bib", {})

        title = clean_text(bib.get("title"))
        if not title:
            continue

        publications.append({
            "title": title,
            "authors": clean_text(bib.get("author")),
            "venue": clean_text(
                bib.get("journal")
                or bib.get("conference")
                or bib.get("venue")
                or bib.get("publisher")
            ),
            "year": clean_text(bib.get("pub_year")),
        })

    publications.sort(
        key=lambda x: int(x["year"]) if x["year"].isdigit() else 0,
        reverse=True
    )

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
        "<!-- This page is automatically generated. -->",
        "<!-- Add optional manual details in _data/publication_notes.yml. -->",
        "",
    ]

    for pub in publications:
        title = pub["title"]
        extra = notes.get(title, {}) or {}

        lines.append(f"## {title}  ")
        lines.append("")
        lines.append('<p style="font-size: 90%;">')

        authors = extra.get("authors") or pub["authors"]
        venue = extra.get("venue") or pub["venue"]
        year = extra.get("year") or pub["year"]

        if authors:
            lines.append(f"<strong>Authors:</strong> {authors} <br>")

        if venue:
            lines.append(f"<strong>Venue:</strong> {venue} <br>")

        if year:
            lines.append(f"<strong>Year:</strong> {year} <br>")

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
            add_link_or_text(lines, label, extra.get(key))

        lines.append("</p>")
        lines.append("")
        lines.append('<hr style="border: 1px solid #ddd; margin: 2em 0;" />')
        lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Updated {OUT} with {len(publications)} publications.")


if __name__ == "__main__":
    main()
