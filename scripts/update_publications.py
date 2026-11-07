#!/usr/bin/env python3
"""Update a Jekyll publications page from Google Scholar with metadata fallbacks.

Run: python scripts/update_publications.py
Dependencies: scholarly, PyYAML, requests (and their dependencies).
Exit codes: 0 = published; 1 = extraction/incomplete metadata error; 124 = timeout.
"""
from __future__ import annotations

import html
import json
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote

import requests
import yaml
from scholarly import scholarly

SCHOLAR_ID = "xqccd64AAAAJ"
OUT = Path("_pages/publication.md")
NOTES_FILE = Path("_data/publication_notes.yml")  # Optional; no new YAML file required
MAX_PUBLICATIONS = 150
MAX_RUNTIME_SECONDS = 300
DETAIL_ATTEMPTS = 2
HTTP_TIMEOUT = (5, 12)  # connection timeout, read timeout (seconds)
STRICT_METADATA = True  # Do not replace existing page if required fields are missing
# For proceedings or records with no conventional venue, set venue in optional notes.

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "PublicationPageUpdater/1.0 (academic metadata lookup)", "Accept": "application/json"})


def clean(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(filter(None, (clean(v) for v in value)))
    return re.sub(r"\s+", " ", str(value)).strip()


def esc(value):
    return html.escape(clean(value), quote=True)


def as_int(value):
    try:
        return int(str(value))
    except (ValueError, TypeError):
        return 0


def valid_year(value):
    m = re.search(r"\b(?:19|20)\d{2}\b", clean(value))
    return m.group(0) if m else ""


def norm_title(value):
    return re.sub(r"[^a-z0-9]", "", clean(value).casefold())


def title_match(a, b):
    x, y = norm_title(a), norm_title(b)
    return bool(x and y) and (x == y or (min(len(x), len(y)) >= 25 and SequenceMatcher(None, x, y).ratio() >= 0.96))


def author_field(value):
    result = clean(value)
    if not result:
        return ""
    invalid = ("proceedings of", "international conference", "conference on", "journal of", "lecture notes", "transactions on", "springer", "arxiv")
    if any(term in result.casefold() for term in invalid):
        return ""
    return result


def venue_field(bib):
    for field in ("journal", "conference", "booktitle", "venue", "publisher"):
        v = clean(bib.get(field))
        if v:
            return v
    return ""  # Do not confuse formatted citation text with venue


def parse_scholar(pub):
    bib = pub.get("bib") or {}
    return {
        "title": clean(bib.get("title")),
        "authors": author_field(bib.get("author")),
        "venue": venue_field(bib),
        "year": valid_year(bib.get("pub_year") or bib.get("year")),
        "citations": as_int(pub.get("num_citations")),
        "paper": clean(pub.get("pub_url")),
        "pdf": clean(pub.get("eprint_url")),
        "doi": "",
    }


def missing(pub):
    return [key for key in ("title", "authors", "venue", "year") if not clean(pub.get(key))]


def fill_empty(dst, src, label):
    added = []
    for key in ("authors", "venue", "year", "paper", "pdf", "doi"):
        if not clean(dst.get(key)) and clean(src.get(key)):
            dst[key] = clean(src[key])
            added.append(key)
    if added:
        print(f"  [{label}] recovered: {', '.join(added)}", flush=True)


def http_json(url, params):
    last_error = None
    for attempt in range(2):
        try:
            response = SESSION.get(url, params=params, timeout=HTTP_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(1)
    raise RuntimeError(f"HTTP lookup failed: {last_error}")


def crossref_lookup(title):
    data = http_json("https://api.crossref.org/works", {"query.title": title, "rows": 5})
    for item in data.get("message", {}).get("items", []):
        if not title_match(title, (item.get("title") or [""])[0]):
            continue
        authors = ", ".join(filter(None, (clean(" ".join([a.get("given", ""), a.get("family", "")])) for a in item.get("author", []))))
        dates = (item.get("published") or {}).get("date-parts") or []
        year = str(dates[0][0]) if dates and dates[0] else ""
        doi = clean(item.get("DOI"))
        return {"authors": authors, "venue": clean(item.get("container-title")), "year": year,
                "doi": f"https://doi.org/{doi}" if doi else "", "paper": clean(item.get("URL"))}
    return {}


def openalex_lookup(title):
    data = http_json("https://api.openalex.org/works", {"search": title, "per-page": 5})
    for item in data.get("results", []):
        if not title_match(title, item.get("display_name")):
            continue
        authors = ", ".join(filter(None, (clean((entry.get("author") or {}).get("display_name")) for entry in item.get("authorships", []))))
        location = item.get("primary_location") or {}
        source = location.get("source") or {}
        return {"authors": authors, "venue": clean(source.get("display_name")),
                "year": valid_year(item.get("publication_year")), "doi": clean(item.get("doi")),
                "paper": clean(location.get("landing_page_url")), "pdf": clean(location.get("pdf_url"))}
    return {}


def load_notes():
    if not NOTES_FILE.exists():
        return {}
    with NOTES_FILE.open(encoding="utf-8") as f:
        notes = yaml.safe_load(f) or {}
    if not isinstance(notes, dict):
        raise ValueError(f"{NOTES_FILE} must contain a mapping of publication titles to metadata")
    return notes


def apply_notes(pub, notes):
    note = notes.get(pub["title"], {}) or {}
    if not isinstance(note, dict):
        raise ValueError(f"Notes for {pub['title']!r} must be a mapping")
    for key in ("authors", "venue", "year", "citations", "paper", "pdf", "preprint", "code", "slides", "video", "doi", "arxiv", "date", "status", "proceedings", "series", "pages", "note"):
        if key in note and note[key] is not None:
            pub[key] = clean(note[key])
    return pub


def extract():
    print("Fetching Google Scholar profile...", flush=True)
    author = scholarly.search_author_id(SCHOLAR_ID)
    author = scholarly.fill(author, sections=["basics", "indices", "publications"], publication_limit=MAX_PUBLICATIONS)
    raw = author.get("publications") or []
    if not raw:
        raise RuntimeError("Google Scholar returned no publications")
    print(f"Scholar returned {len(raw)} publications", flush=True)
    notes = load_notes()
    result = []
    for i, item in enumerate(raw, 1):
        pub = parse_scholar(item)
        if not pub["title"]:
            raise RuntimeError(f"Publication {i} has no title; refusing partial update")
        print(f"[{i}/{len(raw)}] {pub['title']}", flush=True)
        if missing(pub):
            # The NoneType.text error indicates an incompatible/empty Scholar page;
            # retrying every publication is wasteful. Disable further detailed fills.
            global detail_disabled
            if not detail_disabled:
                for attempt in range(DETAIL_ATTEMPTS):
                    try:
                        detailed = scholarly.fill(item)
                        fill_empty(pub, parse_scholar(detailed), "Scholar details")
                        break
                    except Exception as exc:
                        print(f"  [Scholar details failed] {type(exc).__name__}: {exc}", flush=True)
                        if isinstance(exc, (AttributeError, TypeError)) and "NoneType" in str(exc):
                            detail_disabled = True
                            print("  [INFO] Disabling further Scholar detail requests; using metadata APIs", flush=True)
                            break
                        if attempt + 1 < DETAIL_ATTEMPTS:
                            time.sleep(1)
        if missing(pub):
            for name, lookup in (("Crossref", crossref_lookup), ("OpenAlex", openalex_lookup)):
                if not missing(pub):
                    break
                try:
                    fill_empty(pub, lookup(pub["title"]), name)
                except Exception as exc:
                    print(f"  [{name} unavailable] {exc}", flush=True)
        apply_notes(pub, notes)
        if missing(pub):
            print(f"  [INCOMPLETE] Missing: {', '.join(missing(pub))}", flush=True)
        result.append(pub)
        time.sleep(random.uniform(0.5, 1.0))
    result.sort(key=lambda p: as_int(p.get("year")), reverse=True)
    return author, result


detail_disabled = False

CSS = """
<style>
.pub-metrics{display:flex;gap:1rem;flex-wrap:wrap;margin:1.2rem 0 2rem}
.pub-metric-card{flex:1;min-width:140px;padding:1rem;border:1px solid #e5e7eb;border-radius:12px;background:#f8fafc;text-align:center}
.pub-metric-number{font-size:1.45rem;font-weight:700}.pub-metric-label{font-size:.8rem;color:#64748b}
.pub-toolbar{display:flex;justify-content:space-between;align-items:center;gap:1rem;margin:1.5rem 0;padding:.8rem 1rem;border:1px solid #e5e7eb;border-radius:12px;background:#f8fafc}
.pub-toolbar label{font-size:.9rem;font-weight:600}.pub-toolbar select{padding:.4rem .65rem;border-radius:8px;border:1px solid #cbd5e1;background:white}
.pub-card{padding:1.15rem 1.25rem;margin:1.15rem 0;border:1px solid #e5e7eb;border-radius:14px;background:#fff;box-shadow:0 2px 8px rgba(15,23,42,.04)}
.pub-title{font-size:1.12rem;font-weight:700;margin-bottom:.45rem}.pub-authors{font-size:.92rem;color:#334155;margin-bottom:.35rem}
.pub-meta{font-size:.88rem;color:#475569;margin-bottom:.65rem}.pub-note{font-size:.88rem;color:#334155;background:#f8fafc;border-left:3px solid #cbd5e1;padding:.55rem .75rem;margin:.7rem 0}
.pub-links{margin-top:.7rem}.pub-btn{display:inline-block;padding:.28rem .62rem;margin:.15rem .25rem .15rem 0;border:1px solid #cbd5e1;border-radius:999px;font-size:.78rem;text-decoration:none}.pub-btn:hover{background:#f1f5f9}
.pub-updated{font-size:.8rem;color:#64748b}
</style>
"""
JS = """
<script>
document.addEventListener('DOMContentLoaded',function(){
 const select=document.getElementById('pub-sort'),list=document.getElementById('pub-list');
 if(!select||!list)return;
 select.addEventListener('change',function(){
  const cards=Array.from(list.querySelectorAll('.pub-card'));
  cards.sort(function(a,b){
   if(select.value==='year-desc')return Number(b.dataset.year||0)-Number(a.dataset.year||0);
   if(select.value==='year-asc')return Number(a.dataset.year||0)-Number(b.dataset.year||0);
   if(select.value==='citations-desc')return Number(b.dataset.citations||0)-Number(a.dataset.citations||0);
   return 0;
  });
  cards.forEach(card=>list.appendChild(card));
 });
});
</script>
"""


def button(label, url):
    if not url:
        return ""
    # Only permit normal web URLs in generated anchors.
    if not re.match(r"^https?://", clean(url), flags=re.I):
        return ""
    return f'<a class="pub-btn" href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(label)}</a>'


def build_page(author, publications):
    updated = datetime.now(timezone.utc).strftime("%B %d, %Y, %H:%M UTC")
    lines = ["---", "title: Publications", "layout: archive", "classes: wide", "permalink: /publication/", "author_profile: true", "excerpt: This page shows a list of Javad Pourmostafa's papers and talks.", "---", "", CSS,
             "", "I have published under the name **Javad Pourmostafa Roshan Sharami**, where *Roshan Sharami* is a suffix added to my last name.", "",
             f'<p class="pub-updated"><em>Last updated: {updated}</em></p>', "", '<div class="pub-metrics">']
    for label, value in (("Citations", author.get("citedby")), ("h-index", author.get("hindex")), ("i10-index", author.get("i10index")), ("Publications", len(publications))):
        lines.append(f'<div class="pub-metric-card"><div class="pub-metric-number">{esc(value if value is not None and value != "" else "—")}</div><div class="pub-metric-label">{esc(label)}</div></div>')
    lines += ["</div>", "", '<div class="pub-toolbar">', '<label for="pub-sort">Sort publications</label>', '<select id="pub-sort">', '<option value="year-desc">Newest first</option>', '<option value="year-asc">Oldest first</option>', '<option value="citations-desc">Most cited first</option>', '</select>', '</div>', '', '<div id="pub-list">']
    for pub in publications:
        lines.append(f'<div class="pub-card" data-year="{as_int(pub.get("year"))}" data-citations="{as_int(pub.get("citations"))}">')
        lines.append(f'<div class="pub-title">{esc(pub["title"])}</div>')
        if pub.get("authors"):
            lines.append(f'<div class="pub-authors">{esc(pub["authors"])}</div>')
        meta = [esc(pub[k]) for k in ("venue", "year") if pub.get(k)]
        if pub.get("citations") is not None and pub.get("citations") != "":
            meta.append(f'{esc(pub["citations"])} citations')
        if meta:
            lines.append(f'<div class="pub-meta">{" · ".join(meta)}</div>')
        for field in ("date", "status", "proceedings", "series", "pages"):
            if pub.get(field):
                lines.append(f'<div class="pub-meta"><strong>{field.capitalize()}:</strong> {esc(pub[field])}</div>')
        if pub.get("note"):
            lines.append(f'<div class="pub-note">{esc(pub["note"])}</div>')
        links = [button(label, pub.get(key)) for key, label in (("paper", "Paper"), ("pdf", "PDF"), ("preprint", "Preprint"), ("code", "Code"), ("slides", "Slides"), ("video", "Video"), ("doi", "DOI"), ("arxiv", "arXiv"))]
        if any(links):
            lines.append('<div class="pub-links">' + ' '.join(filter(None, links)) + '</div>')
        lines += ["</div>", ""]
    lines += ["</div>", JS]
    return "\n".join(lines)


def worker():
    try:
        author, publications = extract()
        incomplete = [(p["title"], missing(p)) for p in publications if missing(p)]
        print("\nPUBLICATION EXTRACTION SUMMARY", flush=True)
        print(f"Total: {len(publications)} | Complete: {len(publications)-len(incomplete)} | Incomplete: {len(incomplete)}", flush=True)
        print(f"Citations: {author.get('citedby', '')} | h-index: {author.get('hindex', '')} | i10-index: {author.get('i10index', '')}", flush=True)
        for title, fields in incomplete:
            print(f"[INCOMPLETE] {title} | missing: {', '.join(fields)}", flush=True)
        if incomplete and STRICT_METADATA:
            print("[ERROR] Required metadata incomplete. Existing publication page preserved.", flush=True)
            return 1
        if len(publications) >= MAX_PUBLICATIONS:
            print("[WARNING] Publication limit reached; check for truncated profile", flush=True)
        page = build_page(author, publications)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        temp = OUT.with_suffix(OUT.suffix + ".tmp")
        temp.write_text(page, encoding="utf-8")
        temp.replace(OUT)
        print(f"[SUCCESS] Updated {OUT}", flush=True)
        return 0
    except Exception as exc:
        print(f"[ERROR] {type(exc).__name__}: {exc}. Existing page preserved.", flush=True)
        return 1


def main():
    if os.environ.get("_PUBLICATION_WORKER") == "1":
        return worker()
    env = dict(os.environ, _PUBLICATION_WORKER="1", PYTHONUNBUFFERED="1")
    print(f"Starting extraction with hard {MAX_RUNTIME_SECONDS}-second timeout...", flush=True)
    try:
        proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve())], env=env)
        try:
            return proc.wait(timeout=MAX_RUNTIME_SECONDS)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            print(f"[TIMEOUT] Extraction exceeded {MAX_RUNTIME_SECONDS} seconds. Existing page preserved unless writing was already completed.", flush=True)
            return 124
    except Exception as exc:
        print(f"[ERROR] Could not start extraction: {exc}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
