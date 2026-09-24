"""Scrapes the cook's saved-recipe collections (TikTok collection + Pinterest
board) into raw items: {id, fuente, url, caption, thumb}. No LLM here — turning
captions into structured catalog entries is recipe_refs.py's job.

Both sources are private-ish: probed logged-out on 2026-09-23, TikTok answers
"Esta colección no está disponible" and Pinterest only renders ~24 "gated" pin
previews with no /pin/ links at all. So scraping always runs on a dedicated,
persistent Chromium profile (data/browser_profile/) that the cook logs into
once via `python main.py actualizar-recetas-ref --login`. Cookies then persist
for later headless runs.

Selenium, not Playwright: the project already depends on Selenium + the system
Chromium for costco_scraper.py — same driver setup, no new dependency.
"""
import re
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

from .costco_scraper import _find_chromium_binary

PROFILE_DIR = Path("data/browser_profile").resolve()

SOURCES = {
    "tiktok": {
        "url": "https://www.tiktok.com/@adanttmm/collection/Recetas-7627353247623269140",
        "login_url": "https://www.tiktok.com/login",
        "link_selector": 'a[href*="/video/"], a[href*="/photo/"]',
        "id_re": re.compile(r"/(?:video|photo)/(\d+)"),
    },
    "pinterest": {
        "url": "https://mx.pinterest.com/adanttmm/cocina/",
        "login_url": "https://mx.pinterest.com/login/",
        "link_selector": 'a[href*="/pin/"]',
        "id_re": re.compile(r"/pin/(\d+)"),
    },
}

SCROLL_PAUSE_S = 2.0
# Stop scrolling after this many scrolls in a row add nothing new (end of the grid
# or lazy-load stalled).
IDLE_SCROLLS_TO_STOP = 3
# Incremental mode: collections list newest first, so once this many already-
# cataloged items have been seen in a row, everything further down is old too.
KNOWN_IN_A_ROW_TO_STOP = 40
MAX_SCROLLS = 300

_LOGIN_WALL_RE = re.compile(r"Iniciar sesión|Inicia sesión|Log in|no está disponible", re.IGNORECASE)


class LoginRequired(RuntimeError):
    pass


def _binary() -> str:
    binary = _find_chromium_binary()
    if not binary:
        raise RuntimeError(
            "No se encontró Chromium/Chrome — instálalo (p. ej. `sudo snap install chromium`)."
        )
    return binary


def open_login_browser() -> None:
    """Open a normal (non-automated) Chromium window on the scraper's profile with
    both login pages, and block until the cook closes it. A plain subprocess, not
    Selenium: sites (Google sign-in especially) refuse logins in a window flagged
    as "controlled by automated software"."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        _binary(),
        f"--user-data-dir={PROFILE_DIR}",
        "--password-store=basic",
        "--no-first-run",
        "--new-window",
        *(s["login_url"] for s in SOURCES.values()),
    ], check=False)


@contextmanager
def _driver(headless: bool = True):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    if not PROFILE_DIR.exists():
        raise LoginRequired(
            "No hay sesión guardada — corre primero `python main.py actualizar-recetas-ref --login`."
        )
    opts = Options()
    opts.binary_location = _binary()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument(f"--user-data-dir={PROFILE_DIR}")
    # Must match open_login_browser(): cookies are encrypted with the password-
    # store key, and a headless run can't reach the desktop keyring the login
    # window used — it would fall back to a different key, fail to decrypt the
    # session cookies and look logged out. Pinning "basic" on both sides makes
    # the saved login readable headless.
    opts.add_argument("--password-store=basic")
    # Different port from costco_scraper (9222) so the two never collide.
    opts.add_argument("--remote-debugging-port=9225")
    opts.add_argument("--window-size=1400,2000")
    opts.add_argument("--lang=es-MX")
    # Headless Chrome's default UA says "HeadlessChrome" and TikTok serves it a
    # captcha/empty grid — present as the regular desktop browser instead.
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    )
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])

    d = webdriver.Chrome(options=opts)
    d.set_page_load_timeout(45)
    try:
        yield d
    finally:
        d.quit()


def _collect_visible(driver, cfg: dict, source: str, found: dict) -> int:
    """Add every not-yet-seen item currently in the DOM to `found` (insertion
    order = page order). Returns how many were new."""
    from selenium.webdriver.common.by import By

    new = 0
    for a in driver.find_elements(By.CSS_SELECTOR, cfg["link_selector"]):
        try:
            href = a.get_attribute("href") or ""
            m = cfg["id_re"].search(href)
            if not m:
                continue
            item_id = f"{source}-{m.group(1)}"
            if item_id in found:
                continue
            imgs = a.find_elements(By.TAG_NAME, "img")
            img = imgs[0] if imgs else None
            caption = " ".join(filter(None, [
                a.get_attribute("aria-label") or "",
                (img.get_attribute("alt") if img else "") or "",
                a.text or "",
            ]))
            found[item_id] = {
                "id": item_id,
                "fuente": source,
                "url": href.split("?")[0],
                "caption": re.sub(r"\s+", " ", caption).strip()[:400],
                "thumb": (img.get_attribute("src") if img else "") or "",
            }
            new += 1
        except Exception:  # noqa: BLE001 — node detached mid-scroll; next pass picks it up
            continue
    return new


def _pinterest_board_size(body_text: str) -> int | None:
    """A logged-in board page appends "Más ideas" recommendations (not the cook's
    pins) after the board's own pins, in the same grid. The header's "N Pines"
    count is the only reliable boundary, so collection is capped at it."""
    m = re.search(r"([\d.,]+)\s+Pines?\b", body_text)
    return int(re.sub(r"[.,]", "", m.group(1))) if m else None


def scrape_source(source: str, known_ids: set, full: bool = False,
                  headless: bool = True, log=print) -> list[dict]:
    """Return the collection's items in page order (newest first). With
    full=False, stops early once KNOWN_IN_A_ROW_TO_STOP cataloged items appear
    in a row — the cheap weekly path. full=True scrolls to the very end."""
    from selenium.webdriver.common.by import By

    cfg = SOURCES[source]
    found: dict = {}
    with _driver(headless=headless) as d:
        d.get(cfg["url"])
        time.sleep(6)
        body = d.find_element(By.TAG_NAME, "body").text
        cap = _pinterest_board_size(body) if source == "pinterest" else None

        idle = 0
        for _ in range(MAX_SCROLLS):
            new = _collect_visible(d, cfg, source, found)
            idle = idle + 1 if new == 0 else 0
            if idle >= IDLE_SCROLLS_TO_STOP:
                break
            if cap and len(found) >= cap:
                break
            if not full:
                ids = list(found)
                tail = 0
                for i in reversed(ids):
                    if i not in known_ids:
                        break
                    tail += 1
                if tail >= KNOWN_IN_A_ROW_TO_STOP:
                    break
            d.execute_script("window.scrollBy(0, Math.floor(window.innerHeight * 0.9));")
            time.sleep(SCROLL_PAUSE_S)

        if not found and _LOGIN_WALL_RE.search(d.find_element(By.TAG_NAME, "body").text):
            raise LoginRequired(
                f"{source}: la página pide iniciar sesión — corre "
                "`python main.py actualizar-recetas-ref --login` y entra a tu cuenta."
            )

    items = list(found.values())
    if cap:
        items = items[:cap]
    log(f"{source}: {len(items)} publicaciones leídas" + (f" (tablero de {cap})" if cap else ""))
    return items

