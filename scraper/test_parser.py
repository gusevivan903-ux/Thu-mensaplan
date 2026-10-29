"""Schneller Selbsttest für den Parser: python scraper/test_parser.py"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from fetch_mensa import parse_day_html  # noqa: E402

items = parse_day_html((Path(__file__).parent / "fixtures" / "sample.html").read_text(encoding="utf-8"))
assert len(items) == 3, items
a, b, c = items
assert a["category"] == "Topf und Pfanne"
assert a["name"] == "Farfalle-Spinat-Pfanne mit Kirschtomaten in Käsesahne"
assert a["prices"] == {"student": 3.9, "staff": 5.95, "guest": 7.45}
assert a["nutrition"]["kcal"] == 648 and a["nutrition"]["protein"] == 21.4
assert a["nutrition"]["satFat"] == 11.3 and a["nutrition"]["sugar"] == 9.6
assert "vegetarisch" in a["tags"] and a["allergens"] == ["24", "34W"]
assert b["name"] == "Hähnchenbrust, Kräuterreis und Paprikagemüse"
assert b["nutrition"]["protein"] == 42.8 and "Geflügel" in b["tags"]
assert c["nutrition"] is None and "vegan" in c["tags"]
print("Parser-Test OK ✔")
