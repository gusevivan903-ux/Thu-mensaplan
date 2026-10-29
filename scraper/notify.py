#!/usr/bin/env python3
"""
Schickt mittags eine Push-Nachricht mit dem Mensa-Tagessieger aufs Handy (über ntfy.sh).

Bewertung = dieselbe wie auf der Webseite (docs/index.html).

Einstellungen über Umgebungsvariablen (in GitHub: Settings → Secrets and variables → Actions):
  NTFY_TOPIC        (Secret, Pflicht)  dein geheimer Kanalname, z. B. mensa-ivan-x7k29q
  MENSA_STANDORT    (Variable)  prittwitz | eselsberg | beide      Standard: prittwitz
  MENSA_PRESET      (Variable)  ausgewogen | gym | pleite | gesund  Standard: ausgewogen
  MENSA_ERNAEHRUNG  (Variable)  alle | vegetarisch | vegan          Standard: alle
  MENSA_PREISGRUPPE (Variable)  student | staff | guest             Standard: student
  PAGES_URL         Link, der beim Antippen geöffnet wird (setzt der Workflow automatisch)

Aufruf:
  python scraper/notify.py --dry-run --date 2026-10-19     # nur anzeigen, nichts senden
  python scraper/notify.py --force                          # sofort senden (Test)
  python scraper/notify.py                                  # sendet nur zwischen 11:00 und 11:59 Uhr (Berlin)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
PRESETS = {
    "ausgewogen": (35, 40, 25),
    "gym": (15, 70, 15),
    "pleite": (70, 20, 10),
    "gesund": (15, 30, 55),
}
SEND_WINDOW = (11, 0, 11, 59)  # Stunde/Minute von – bis (Berlin)


# ------------------------------------------------------------ Bewertung (wie index.html)
def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def lin(v: float, good: float, bad: float) -> float:
    return clamp01((bad - v) / (bad - good))


def nutri_score(n: dict | None) -> float | None:
    if not n:
        return None
    parts = []
    k = n.get("kcal")
    if k is not None:
        if 450 <= k <= 850:
            parts.append(1.0)
        elif k < 450:
            parts.append(clamp01((k - 250) / 200))
        else:
            parts.append(clamp01((1200 - k) / 350))
    if n.get("satFat") is not None:
        parts.append(lin(n["satFat"], 5, 15))
    if n.get("sugar") is not None:
        parts.append(lin(n["sugar"], 10, 30))
    if n.get("salt") is not None:
        parts.append(lin(n["salt"], 2, 5))
    return sum(parts) / len(parts) if parts else None


def price_of(item: dict, group: str) -> float | None:
    p = item.get("prices") or {}
    v = p.get(group)
    if v is None and group == "staff":
        v = p.get("student")
    return v


def rank(items: list[dict], weights: tuple[int, int, int], group: str) -> list[dict]:
    prices = [x for x in (price_of(i, group) for i in items) if x and x > 0]
    min_p = min(prices) if prices else None
    prots = [x for x in ((i.get("nutrition") or {}).get("protein") for i in items) if x and x > 0]
    max_pr = max(prots) if prots else None
    wp, wpr, wn = weights
    wsum = (wp + wpr + wn) or 1

    out = []
    for it in items:
        price = price_of(it, group)
        prot = (it.get("nutrition") or {}).get("protein")
        s_price = (min_p / price) if (price and price > 0 and min_p) else None
        s_prot = (prot / max_pr) if (prot is not None and max_pr) else None
        s_nutri = nutri_score(it.get("nutrition"))
        total = (wp * (s_price if s_price is not None else 0.5)
                 + wpr * (s_prot if s_prot is not None else 0.5)
                 + wn * (s_nutri if s_nutri is not None else 0.5)) / wsum
        out.append({"it": it, "price": price, "total": total})
    out.sort(key=lambda r: (-r["total"], r["price"] if r["price"] is not None else 99))
    return out


# ------------------------------------------------------------ Text bauen
def de(v: float | None, digits: int = 0) -> str:
    if v is None:
        return "–"
    return f"{v:.{digits}f}".replace(".", ",")


def short(name: str, n: int = 38) -> str:
    return name if len(name) <= n else name[: n - 1].rstrip(" ,") + "…"


def diet_filter(items: list[dict], diet: str) -> list[dict]:
    if diet == "vegan":
        return [i for i in items if "vegan" in (i.get("tags") or [])]
    if diet == "vegetarisch":
        return [i for i in items if {"vegan", "vegetarisch"} & set(i.get("tags") or [])]
    return items


def build_message(data: dict, day: dt.date, loc_keys: list[str], weights, group: str, diet: str) -> tuple[str, str] | None:
    multi = len(loc_keys) > 1
    blocks, winners = [], []
    for loc in data.get("locations", []):
        if loc["key"] not in loc_keys:
            continue
        d = next((x for x in loc.get("days", []) if x["date"] == day.isoformat()), None)
        items = diet_filter(d["items"] if d else [], diet)
        if not items:
            continue
        ranked = rank(items, weights, group)
        top = ranked[0]
        winners.append(top["it"]["name"])
        n = top["it"].get("nutrition") or {}
        prot = n.get("protein")
        ppe = prot / top["price"] if prot and top["price"] else None
        lines = []
        if multi:
            lines.append(f"📍 {loc['name'].replace('THU ', '')}: {short(top['it']['name'], 50)}")
        lines.append(
            f"{de(top['price'], 2)} € · {de(prot, 1)} g Protein · {de(n.get('kcal'))} kcal"
            + (f" · {de(ppe, 1)} g/€" if ppe else "")
        )
        for i, r in enumerate(ranked[1:3], start=2):
            rn = r["it"].get("nutrition") or {}
            lines.append(f"{i}. {short(r['it']['name'])} ({de(r['price'], 2)} €, {de(rn.get('protein'), 0)} g)")
        blocks.append("\n".join(lines))
    if not blocks:
        return None
    title = "🍽️ Mensa-Sieger heute" if multi else f"🏆 {short(winners[0], 60)}"
    return title, "\n\n".join(blocks)


# ------------------------------------------------------------ Senden
def send_ntfy(topic: str, title: str, message: str, click: str | None, server: str) -> None:
    import requests

    payload = {
        "topic": topic,
        "title": title,
        "message": message,
        "tags": ["fork_and_knife"],
        "priority": 3,
    }
    if click:
        payload["click"] = click
        payload["actions"] = [{"action": "view", "label": "Ranking öffnen", "url": click}]
    r = requests.post(server.rstrip("/") + "/", data=json.dumps(payload).encode("utf-8"),
                      headers={"Content-Type": "application/json"}, timeout=20)
    r.raise_for_status()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="docs/data/mensa.json")
    ap.add_argument("--date", help="Tag YYYY-MM-DD (Standard: heute, Berlin)")
    ap.add_argument("--dry-run", action="store_true", help="Nur anzeigen, nicht senden")
    ap.add_argument("--force", action="store_true", help="Zeitfenster ignorieren")
    args = ap.parse_args()

    now = dt.datetime.now(BERLIN)
    if not (args.force or args.dry_run):
        h1, m1, h2, m2 = SEND_WINDOW
        if not ((now.hour, now.minute) >= (h1, m1) and (now.hour, now.minute) <= (h2, m2)):
            print(f"Jetzt ist {now:%H:%M} Uhr in Berlin – außerhalb des Sendefensters, keine Push-Nachricht.")
            return 0

    day = dt.date.fromisoformat(args.date) if args.date else now.date()
    standort = os.environ.get("MENSA_STANDORT", "prittwitz").strip().lower() or "prittwitz"
    loc_keys = ["prittwitz", "eselsberg"] if standort == "beide" else [standort]
    preset = os.environ.get("MENSA_PRESET", "ausgewogen").strip().lower() or "ausgewogen"
    weights = PRESETS.get(preset, PRESETS["ausgewogen"])
    group = os.environ.get("MENSA_PREISGRUPPE", "student").strip().lower() or "student"
    diet = os.environ.get("MENSA_ERNAEHRUNG", "alle").strip().lower() or "alle"

    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    built = build_message(data, day, loc_keys, weights, group, diet)
    if built is None and args.force:
        # Test-Push am Wochenende o. Ä.: nächsten Tag mit Speiseplan nehmen (sonst den letzten)
        dates = sorted({d["date"] for l in data.get("locations", []) for d in l.get("days", []) if d.get("items")})
        pick = next((x for x in dates if x >= day.isoformat()), dates[-1] if dates else None)
        if pick:
            day = dt.date.fromisoformat(pick)
            built = build_message(data, day, loc_keys, weights, group, diet)
            if built:
                built = (built[0], f"(Test – Plan vom {day:%d.%m.})\n" + built[1])
    if built is None:
        print(f"Für {day} gibt's keinen Speiseplan (oder nichts passt zum Filter) – keine Nachricht.")
        return 0
    title, message = built
    if data.get("demo"):
        message += "\n\n(Demo-Daten – echter Plan folgt nach dem ersten Abruf)"

    print("TITEL:", title)
    print(message)
    if args.dry_run:
        return 0

    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        print("Kein NTFY_TOPIC gesetzt – Push übersprungen. (Secret in GitHub anlegen, siehe README)", file=sys.stderr)
        return 0
    send_ntfy(topic, title, message, os.environ.get("PAGES_URL") or None,
              os.environ.get("NTFY_SERVER", "https://ntfy.sh"))
    print("Push gesendet ✔")
    return 0


if __name__ == "__main__":
    sys.exit(main())
