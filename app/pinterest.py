"""Links rastreáveis do Pinterest para a página de vendas."""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlencode, urlsplit, urlunsplit


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-") or "receita"


def pin_link(base_url: str, slug: str, variant: str = "") -> str:
    """https://site/?src=pin-<slug> ; no A/B: pin-<slug>-a, -b, -c."""
    src = f"pin-{slug}" + (f"-{variant.lower()}" if variant else "")
    scheme, netloc, path, _query, _frag = urlsplit(base_url)
    return urlunsplit((scheme, netloc, path or "/", urlencode({"src": src}), ""))
