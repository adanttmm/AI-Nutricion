"""Free, local alternative to LLM web search for verifying packaged/specialty
ingredients against Costco México's own site search (www.costco.com.mx).

Scope — deliberately NOT used for fresh produce/meat/fish/dairy: Costco's
e-commerce catalog only lists items that have their own online SKU (branded,
packaged, shelf-stable goods). Loose warehouse perishables — the actual
tomatoes, salmon fillets, chicken breast you'd buy in-store — mostly have no
product page at all, so a search for them returns a false "no encontrado".
Confirmed by hand: searching "jitomate" or "salmon" on costco.com.mx returns
no/irrelevant results despite both being genuine Costco staples. Callers
(shopping_validator.py) must only send Despensa-type rows here, never
Perecedero ones — the caller does that filtering, this module trusts its
input.
"""
import re
import shutil
import tempfile
import time
import unicodedata
import urllib.parse
from contextlib import contextmanager

SEARCH_URL = "https://www.costco.com.mx/search?q={query}"
WAIT_TIMEOUT_S = 10
POLL_INTERVAL_S = 0.5

# Costco's own search does loose substring matching — "sal" (salt) matches
# "Sala" (living-room furniture) — and the results page also renders a
# sitewide "featured" carousel (an iPhone ad showed up on every unrelated
# query) that looks like a search result to a naive `a[href*="/p/"]` scrape.
# Without a relevance filter, both make "found" untrustworthy — a false
# "sí lo vende" is worse than a false "no lo vende" (which just falls back to
# the LLM), so titles are only accepted if a real query word appears as a
# whole word in them.
_STOPWORDS = {"de", "la", "el", "los", "las", "en", "y", "con", "para", "sin", "al", "del", "a", "o"}


def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s.lower()


def _significant_words(query: str) -> list[str]:
    words = re.findall(r"[a-zA-Záéíóúñ]+", query.lower())
    return [w for w in (_normalize(w) for w in words) if w not in _STOPWORDS and len(w) > 2]


def _is_relevant(query_words: list[str], title: str) -> bool:
    if not query_words:
        return True
    norm_title = _normalize(title)
    return any(re.search(rf"\b{re.escape(w)}\b", norm_title) for w in query_words)


def _find_chromium_binary() -> str | None:
    for name in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        path = shutil.which(name)
        if path:
            return path
    # Ubuntu's snap-wrapped chromium isn't always on PATH.
    snap_path = "/snap/bin/chromium"
    if __import__("os").path.exists(snap_path):
        return snap_path
    return None


@contextmanager
def _driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    binary = _find_chromium_binary()
    if not binary:
        raise RuntimeError(
            "No se encontró un binario de Chromium/Chrome instalado — "
            "instala chromium (p. ej. `sudo snap install chromium`) para usar "
            "la verificación local de Costco."
        )

    opts = Options()
    opts.binary_location = binary
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    # Snap-confined Chromium fails to create its default profile dir under
    # this project's execution environment — an explicit, writable
    # --user-data-dir (plus a fixed debug port) avoids the
    # "DevToolsActivePort file doesn't exist" SessionNotCreatedException.
    opts.add_argument(f"--user-data-dir={tempfile.mkdtemp()}")
    opts.add_argument("--remote-debugging-port=9222")
    opts.add_argument("--window-size=1400,1000")
    opts.add_argument("--lang=es-MX")

    d = webdriver.Chrome(options=opts)
    d.set_page_load_timeout(30)
    try:
        yield d
    finally:
        d.quit()


def _wait_for_results(driver) -> str:
    """Poll the rendered body text until the Angular app has resolved the
    search (either a result count or the empty-state message appears), or
    give up at WAIT_TIMEOUT_S and return whatever text is there."""
    from selenium.webdriver.common.by import By

    deadline = time.monotonic() + WAIT_TIMEOUT_S
    body_text = ""
    while time.monotonic() < deadline:
        body_text = driver.find_element(By.TAG_NAME, "body").text
        if "No se encontraron resultados" in body_text or re.search(r"Encontramos [\d,]+ resultados?", body_text):
            break
        time.sleep(POLL_INTERVAL_S)
    return body_text


def _search(driver, query: str) -> dict:
    from selenium.webdriver.common.by import By

    driver.get(SEARCH_URL.format(query=urllib.parse.quote(query)))
    body_text = _wait_for_results(driver)

    if "No se encontraron resultados" in body_text:
        return {"found": False, "count": 0, "top_matches": []}

    m = re.search(r"Encontramos ([\d,]+) resultados?", body_text)
    count = int(m.group(1).replace(",", "")) if m else None

    query_words = _significant_words(query)
    titles: list[str] = []
    for a in driver.find_elements(By.CSS_SELECTOR, "a"):
        href = a.get_attribute("href") or ""
        txt = a.text.strip()
        if txt and "/p/" in href and txt not in titles and _is_relevant(query_words, txt):
            titles.append(txt)
        if len(titles) >= 5:
            break

    # "found" is decided by relevance-filtered titles only — the raw result
    # `count` reflects Costco's own loose match (e.g. "sal" -> 58 furniture
    # results) and is kept solely as informational context, never as a
    # positive signal on its own.
    return {"found": bool(titles), "count": count, "top_matches": titles}


def lookup_many(ingredient_names: list[str]) -> dict[str, dict]:
    """Search costco.com.mx for each ingredient name, reusing a single
    browser session (much faster than relaunching Chromium per item).

    Returns {name: {"found": bool, "count": int|None, "top_matches": [...]}}.
    On a per-item failure (page error, etc.) that item's entry instead has
    {"found": None, "error": "..."} — the caller should treat None as
    "couldn't verify" (fall back to the LLM), never as "not found".
    """
    results: dict[str, dict] = {}
    with _driver() as d:
        for name in ingredient_names:
            try:
                results[name] = _search(d, name)
            except Exception as e:  # noqa: BLE001 — one bad query shouldn't sink the batch
                results[name] = {"found": None, "count": None, "top_matches": [], "error": str(e)}
    return results
