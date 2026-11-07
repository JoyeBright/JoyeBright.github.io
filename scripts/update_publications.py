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
