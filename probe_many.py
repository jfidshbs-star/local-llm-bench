"""Проба многих доменов: robots → sitemap → дочерний sitemap товаров → 2 карточки → есть ли Product JSON-LD с ценой."""
import re, json, sys, gzip, httpx, concurrent.futures as cf
from lxml import html as LH
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36",
      "Accept-Language": "ru-RU,ru;q=0.9"}
def get(c, u):
    r = c.get(u); b = r.content
    if u.endswith(".gz") or b[:2] == b"\x1f\x8b":
        try: b = gzip.decompress(b)
        except Exception: pass
    return r.status_code, b.decode("utf-8", "replace")
locs = lambda x: re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", x)
def products(page):
    out = []
    try: nodes = LH.fromstring(page).xpath('//script[@type="application/ld+json"]/text()')
    except Exception: return out
    for s in nodes:
        try: d = json.loads(s)
        except Exception: continue
        st = [d]
        while st:
            x = st.pop()
            if isinstance(x, list): st += x
            elif isinstance(x, dict):
                t = x.get("@type"); t = t if isinstance(t, list) else [t]
                if "Product" in t: out.append(x)
                st += [v for v in x.values() if isinstance(v, (dict, list))]
    return out
KEYS = ("product", "goods", "tovar", "item", "catalog", "card")
def probe(dom):
    try:
        with httpx.Client(headers=UA, timeout=15, follow_redirects=True) as c:
            code, rb = get(c, f"https://{dom}/robots.txt")
            sms = re.findall(r"(?im)^sitemap:\s*(\S+)", rb) or [f"https://{dom}/sitemap.xml"]
            code, x = get(c, sms[0]); L = locs(x)
            for _ in range(2):
                kids = [u for u in L if re.search(r"\.xml(\.gz)?$", u)]
                if not kids: break
                pick = [u for u in kids if any(k in u.lower() for k in KEYS)] or kids
                code, x = get(c, pick[0]); L = locs(x)
            pages = [u for u in L if not re.search(r"\.xml(\.gz)?$", u)]
            pages = [u for u in pages if any(k in u.lower() for k in KEYS)] or pages
            res = []
            for u in pages[len(pages)//2: len(pages)//2 + 2]:
                code, pg = get(c, u); p = products(pg) if code == 200 else []
                off = p[0].get("offers") if p else None
                if isinstance(off, list): off = off[0] if off else None
                price = off.get("price") if isinstance(off, dict) else None
                res.append(f"{code}/P{len(p)}/price={price}")
            return dom, len(L), res, pages[:1]
    except Exception as e:
        return dom, 0, [type(e).__name__], []
if __name__ == "__main__":
    with cf.ThreadPoolExecutor(8) as ex:
        for r in ex.map(probe, sys.argv[1:]): print(*r)
