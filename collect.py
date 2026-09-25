"""Корпус для теста извлечения: 4 магазина, 50 карточек товара (brandshop.ru выбыл: на карточке нет Product JSON-LD).

Эталон — Product JSON-LD самой страницы. Модели отдаём текст страницы БЕЗ разметки
(скрипты, JSON-LD, стили вырезаны), и сверяем, что она вытащила, с эталоном.
Для каждого поля отмечаем, видно ли значение в тексте: чего на странице нет,
того модель знать не обязана, точность считаем по видимым полям.

Запуск: ../venv/bin/python collect.py   (вежливо: пауза 1,5 с между запросами)
Выход:  corpus/raw/<домен>/<n>.html, corpus/text/<домен>/<n>.txt, corpus/gold.jsonl
"""
import json
import random
import re
import time
from pathlib import Path

import httpx
from lxml import html as LH

from probe_many import UA, get, locs, products

ROOT = Path(__file__).parent / "corpus"
PER_SITE = {"biggeek.ru": 13, "divan.ru": 13, "askona.ru": 12, "velostrana.ru": 12}
MAX_TRIES = 30

# домен → (sitemap, регэксп дочернего sitemap или None, регэксп адреса карточки)
SITES = {
    "biggeek.ru": ("https://biggeek.ru/sitemap.xml", None, r"/products/"),
    "divan.ru": ("https://www.divan.ru/sitemap.xml", r"sitemap\.msk\.xml", r"/product/"),
    "askona.ru": ("https://www.askona.ru/sitemap.xml", r"iblock-2[14]\.xml", r"\.htm\?productId="),
    "velostrana.ru": ("https://www.velostrana.ru/sitemap.xml", None,
                      r"velostrana\.ru/(veloaksessuary|velozapchasti)/[^/]+/[^/]+/$"),
}


def first(x):
    return x[0] if isinstance(x, list) and x else x


def gold_fields(p: dict) -> dict:
    off = first(p.get("offers"))
    if isinstance(off, dict) and off.get("@type") == "AggregateOffer" and off.get("offers"):
        off = first(off["offers"]) or off
    off = off if isinstance(off, dict) else {}
    brand = first(p.get("brand"))
    brand = brand.get("name") if isinstance(brand, dict) else brand
    rating = p.get("aggregateRating") if isinstance(p.get("aggregateRating"), dict) else {}
    price = off.get("price", off.get("lowPrice"))
    avail = str(off.get("availability") or "").rsplit("/", 1)[-1] or None
    return {
        "name": (p.get("name") or "").strip() or None,
        "price": float(str(price).replace(",", ".").replace(" ", "")) if price not in (None, "") else None,
        "currency": off.get("priceCurrency"),
        "brand": (brand or "").strip() or None,
        "sku": str(p.get("sku") or p.get("mpn") or "").strip() or None,
        "availability": avail,
        "rating": float(rating["ratingValue"]) if rating.get("ratingValue") not in (None, "") else None,
        "review_count": int(float(rating.get("reviewCount") or rating.get("ratingCount") or 0)) or None,
    }


def clean_text(page: str) -> str:
    """Видимый текст: без script/style/noscript/svg/template, пробелы схлопнуты."""
    doc = LH.fromstring(page)
    for bad in doc.xpath("//script|//style|//noscript|//svg|//template|//head"):
        bad.drop_tree()
    lines = []
    for chunk in doc.itertext():
        t = re.sub(r"\s+", " ", chunk).strip()
        if t:
            lines.append(t)
    # подряд идущие повторы (меню, хлебные крошки) схлопываем
    out = [ln for i, ln in enumerate(lines) if i == 0 or ln != lines[i - 1]]
    return "\n".join(out)


def norm(s: str) -> str:
    return re.sub(r"[\s  ]+", "", str(s)).lower()


def visible(field: str, val, text: str) -> bool:
    if val is None:
        return False
    t = norm(text)
    if field == "price":
        v = int(val) if float(val).is_integer() else val
        return norm(f"{v:,}".replace(",", " ")) in t or norm(str(v)) in t
    if field == "currency":
        return val == "RUB" and ("₽" in text or "руб" in text.lower())
    if field == "availability":
        # видно, только если наличие написано словами; «В корзину»/«Купить» — не ответ, модель вправе дать null
        return bool(re.search(r"в наличии|нет в наличии|под заказ|распродан|ожидается|нет на складе|предзаказ", text, re.I))
    if field == "rating":
        return str(val).replace(".", ",") in text or str(val) in text
    return norm(val) in t


def main():
    random.seed(24092026)
    ROOT.mkdir(exist_ok=True)
    gold_path = ROOT / "gold.jsonl"
    rows = []
    with httpx.Client(headers=UA, timeout=25, follow_redirects=True) as c:
        for dom, (sm, kid_rx, url_rx) in SITES.items():
            code, x = get(c, sm)
            L = locs(x)
            if kid_rx:
                kids = [u for u in L if re.search(kid_rx, u)]
                L = []
                for k in kids:
                    L += locs(get(c, k)[1])
            cands = [u.replace("&amp;", "&") for u in L if re.search(url_rx, u)]
            random.shuffle(cands)
            kept = tries = 0
            (ROOT / "raw" / dom).mkdir(parents=True, exist_ok=True)
            (ROOT / "text" / dom).mkdir(parents=True, exist_ok=True)
            for u in cands:
                if kept >= PER_SITE[dom] or tries >= MAX_TRIES:
                    break
                tries += 1
                time.sleep(1.5)
                try:
                    code, page = get(c, u)
                except Exception as e:  # сеть — пропускаем карточку
                    print("  skip", type(e).__name__)
                    continue
                ps = products(page) if code == 200 else []
                if not ps:
                    continue
                g = gold_fields(ps[0])
                if g["name"] is None or g["price"] is None:
                    continue
                text = clean_text(page)
                n = kept + 1
                (ROOT / "raw" / dom / f"{n}.html").write_text(page, encoding="utf-8")
                (ROOT / "text" / dom / f"{n}.txt").write_text(text, encoding="utf-8")
                vis = {k: visible(k, v, text) for k, v in g.items()}
                rows.append({"id": f"{dom}/{n}", "url": u, "gold": g, "visible": vis, "chars": len(text)})
                kept += 1
            print(f"{dom}: кандидатов {len(cands)}, попыток {tries}, взято {kept}")
    gold_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    print("всего", len(rows), "→", gold_path)


if __name__ == "__main__":
    main()
