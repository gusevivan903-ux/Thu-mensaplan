#!/usr/bin/env python3
"""
Holt den Speiseplan der THU-Mensen (Studierendenwerk Ulm) und speichert ihn als JSON.

Datenquelle: das Speiseplan-System des Studierendenwerks (maxmanager), dasselbe,
das auf studierendenwerk-ulm.de eingebunden ist. Pro Tag und Standort wird eine
Anfrage gestellt; die Antwort ist HTML, das hier geparst wird.

Aufruf:
    python scraper/fetch_mensa.py --out docs/data/mensa.json --debug-dir debug
    python scraper/fetch_mensa.py --parse-file scraper/fixtures/sample.html   # nur Parser testen
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

BASE = "https://sw-ulm-spl51.maxmanager.xyz"
AJAX_URL = BASE + "/inc/ajax-php_konnektor.inc.php"

LOCATIONS = [
    {"id": 3, "key": "prittwitz", "name": "THU Prittwitzstraße"},
    {"id": 10, "key": "eselsberg", "name": "THU Oberer Eselsberg"},
]

# Kürzel im lang-Attribut, die keine Allergene sind
TAG_CODES = {
    "veg": "vegetarisch",
    "van": "vegan",
    "bio": "bio",
    "S": "Schwein",
    "R": "Rind",
    "L": "Lamm",
    "W": "Wild",
    "G": "Geflügel",
    "F": "Fisch",
    "T": "Tintenfisch",
}

NUM = r"\d+(?:[.,]\d+)?"
PRICE3_RE = re.compile(
    r"(\d+,\d{2})\s*€?\s*\|\s*(\d+,\d{2})\s*€?\s*(?:\|\s*(\d+,\d{2}))?"
)
ALLERGEN_PAREN_RE = re.compile(r"\((?:\s*\d{1,2}\s?[A-Za-z]{0,2}\s*,?)+\)")


# --------------------------------------------------------------------------- Hilfen
def to_float(s: str | None) -> float | None:
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    # "2.711" (Tausenderpunkt) vs "3,5" (Dezimalkomma)
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def direct_text(tag: Tag) -> str:
    """Nur die Textknoten direkt unter dem Tag (ohne Kind-Elemente wie <sup>, .cc, .azn)."""
    parts = [str(c) for c in tag.children if isinstance(c, NavigableString)]
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def clean_name(name: str) -> str:
    name = ALLERGEN_PAREN_RE.sub("", name)
    name = re.sub(r"\s+,", ",", name)
    return re.sub(r"\s+", " ", name).strip(" ,")


# --------------------------------------------------------------------------- Parser
def parse_prices(item: Tag) -> dict:
    text = item.get_text(" ", strip=True)
    m = PRICE3_RE.search(text)
    if not m:
        return {"student": None, "staff": None, "guest": None}
    a, b, c = (to_float(x) for x in m.groups())
    if c is None:  # nur zwei Preise -> Studierende | Gäste
        return {"student": a, "staff": None, "guest": b}
    return {"student": a, "staff": b, "guest": c}


def parse_nutrition(item: Tag) -> dict | None:
    box = item.find("div", class_="azn")
    rows = box.find_all("tr") if box else []
    if not rows:
        return None

    out = {"kcal": None, "protein": None, "fat": None, "satFat": None,
           "carbs": None, "sugar": None, "salt": None}

    def nums(t: str) -> list[float]:
        return [v for v in (to_float(x) for x in re.findall(NUM, t)) if v is not None]

    def kcal_from(t: str) -> float | None:
        m = re.search(rf"({NUM})\s*kcal", t, re.I)
        if m:
            return to_float(m.group(1))
        m = re.search(rf"({NUM})\s*(?:kJ)?\s*/\s*({NUM})", t, re.I)
        if m:
            return to_float(m.group(2))
        n = nums(t)
        return n[-1] if n else None

    order = ["energy", "protein", "fat", "carbs", "salt"]  # Reihenfolge laut Plan
    for i, row in enumerate(rows):
        t = row.get_text(" ", strip=True)
        low = t.lower()
        if "kcal" in low or "brennwert" in low or "energie" in low or "kj" in low:
            kind = "energy"
        elif "eiwei" in low or "protein" in low:
            kind = "protein"
        elif "fett" in low or "fat" in low:
            kind = "fat"
        elif "kohlenhydrat" in low or "carbohydrate" in low:
            kind = "carbs"
        elif "salz" in low or "salt" in low:
            kind = "salt"
        else:
            kind = order[i] if i < len(order) else None

        n = nums(t)
        if kind == "energy":
            out["kcal"] = kcal_from(t)
        elif kind == "protein" and n:
            out["protein"] = n[0]
        elif kind == "fat" and n:
            out["fat"] = n[0]
            out["satFat"] = n[1] if len(n) > 1 else None
        elif kind == "carbs" and n:
            out["carbs"] = n[0]
            out["sugar"] = n[1] if len(n) > 1 else None
        elif kind == "salt" and n:
            out["salt"] = n[0]

    if all(v is None for v in out.values()):
        return None
    return out


def parse_name_and_info(item: Tag) -> tuple[str, str]:
    cc = item.find("div", class_="cc")
    info = cc.get_text(" ", strip=True) if cc else ""
    name = ""
    if cc is not None and isinstance(cc.parent, Tag):
        name = direct_text(cc.parent)
    if not name:
        # Fallback: Element mit dem längsten direkten Text, das kein Preis ist
        best = ""
        for tag in item.find_all(True):
            if tag.get("class") and any(c in ("cc", "azn") for c in tag.get("class")):
                continue
            t = direct_text(tag)
            if PRICE3_RE.search(t) or re.fullmatch(r"[\d\s,.|€/]*", t or "x"):
                continue
            if len(t) > len(best):
                best = t
        name = best
    return clean_name(name), info


def parse_tags(item: Tag) -> tuple[list[str], list[str]]:
    codes = [c.strip() for c in (item.get("lang") or "").split(",") if c.strip()]
    tags = [TAG_CODES[c] for c in codes if c in TAG_CODES]
    allergens = [c for c in codes if c not in TAG_CODES]
    # Fallback über Icons (veg.png / van.png ...)
    for img in item.find_all("img"):
        stem = Path(img.get("src", "")).stem
        if stem in TAG_CODES and TAG_CODES[stem] not in tags:
            tags.append(TAG_CODES[stem])
    if "vegan" in tags and "vegetarisch" not in tags:
        tags.append("vegetarisch")
    return tags, allergens


def parse_day_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    root = soup.find("div", class_="container-fluid") or soup.body or soup
    items: list[dict] = []
    category = ""
    for el in root.find_all("div", recursive=False):
        classes = " ".join(el.get("class") or [])
        if "gruppenkopf" in classes:
            g = el.find("div", class_="gruppenname")
            category = (g or el).get_text(" ", strip=True)
            continue
        if el.get("lang") is None and not el.find("div", class_="azn") and not PRICE3_RE.search(el.get_text(" ")):
            continue  # kein Gericht (Leerzeile, Hinweis o.ä.)
        name, info = parse_name_and_info(el)
        if not name:
            continue
        tags, allergens = parse_tags(el)
        items.append({
            "category": category,
            "name": name,
            "info": info,
            "prices": parse_prices(el),
            "nutrition": parse_nutrition(el),
            "tags": tags,
            "allergens": allergens,
        })
    return items


# --------------------------------------------------------------------------- Abruf
def week_monday(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


def fetch_day(session, loc_id: int, day: dt.date) -> str:
    mon = week_monday(day)
    data = {
        "func": "make_spl",
        "locId": str(loc_id),
        "date": day.isoformat(),
        "lang": "de",
        "startThisWeek": mon.isoformat(),
        "startNextWeek": (mon + dt.timedelta(days=7)).isoformat(),
    }
    r = session.post(AJAX_URL, data=data, timeout=30, headers={
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{BASE}/index.php?locationId={loc_id}",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    })
    r.raise_for_status()
    r.encoding = r.encoding or "utf-8"
    return r.text


def scrape(debug_dir: Path | None, today: dt.date) -> dict:
    import requests

    session = requests.Session()
    session.headers["User-Agent"] = "THU-Mensa-Ranker/1.0 (privates Studi-Projekt)"

    # Tage: Mo–Fr dieser Woche; ab Freitag zusätzlich nächste Woche
    mon = week_monday(today)
    days = [mon + dt.timedelta(days=i) for i in range(5)]
    if today.weekday() >= 4:
        days += [mon + dt.timedelta(days=7 + i) for i in range(5)]

    result = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "demo": False, "locations": []}
    errors = 0
    for loc in LOCATIONS:
        try:
            session.get(f"{BASE}/index.php?locationId={loc['id']}", timeout=30)  # Session-Cookie
        except Exception as e:  # noqa: BLE001
            print(f"[warn] Startseite {loc['id']}: {e}", file=sys.stderr)
        loc_out = {"id": loc["id"], "key": loc["key"], "name": loc["name"], "days": []}
        for day in days:
            try:
                html = fetch_day(session, loc["id"], day)
            except Exception as e:  # noqa: BLE001
                errors += 1
                print(f"[fehler] {loc['name']} {day}: {e}", file=sys.stderr)
                continue
            if debug_dir:
                debug_dir.mkdir(parents=True, exist_ok=True)
                (debug_dir / f"loc{loc['id']}_{day}.html").write_text(html, encoding="utf-8")
            items = parse_day_html(html)
            print(f"{loc['name']} {day}: {len(items)} Gerichte")
            loc_out["days"].append({"date": day.isoformat(), "items": items})
            time.sleep(0.5)
        result["locations"].append(loc_out)

    total = sum(len(d["items"]) for l in result["locations"] for d in l["days"])
    result["stats"] = {"items": total, "errors": errors}
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/data/mensa.json")
    ap.add_argument("--debug-dir", default=None)
    ap.add_argument("--parse-file", help="Nur eine gespeicherte HTML-Antwort parsen und ausgeben")
    ap.add_argument("--date", help="Bezugsdatum YYYY-MM-DD (Standard: heute)")
    args = ap.parse_args()

    if args.parse_file:
        items = parse_day_html(Path(args.parse_file).read_text(encoding="utf-8"))
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return 0

    today = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    data = scrape(Path(args.debug_dir) if args.debug_dir else None, today)
    out = Path(args.out)

    if data["stats"]["items"] == 0 and data["stats"]["errors"] > 0:
        print("Keine Daten geladen – alte Datei bleibt erhalten.", file=sys.stderr)
        return 1

    no_nutri = sum(1 for l in data["locations"] for d in l["days"] for i in d["items"] if not i["nutrition"])
    no_price = sum(1 for l in data["locations"] for d in l["days"] for i in d["items"] if i["prices"]["student"] is None)
    if data["stats"]["items"]:
        print(f"Gesamt: {data['stats']['items']} Gerichte, ohne Nährwerte: {no_nutri}, ohne Preis: {no_price}")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Gespeichert: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
