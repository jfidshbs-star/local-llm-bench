"""Сводка по прогонам extract_bench: точность по полям (только видимые), выдуманные значения, скорость.

Запуск: python report.py results/api-gptoss120b-r1.jsonl [results/другой.jsonl ...]
"""
import json
import statistics as st
import sys
from collections import defaultdict

FIELDS = ["name", "price", "currency", "brand", "sku", "availability", "rating", "review_count"]


def summarize(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    ok, tot, inv = defaultdict(int), defaultdict(int), defaultdict(int)
    site_ok, site_tot = defaultdict(int), defaultdict(int)
    for r in rows:
        site = r["id"].split("/")[0]
        for f, v in r["fields"].items():
            if v["scored"]:
                tot[f] += 1
                site_tot[site] += 1
                if v["ok"]:
                    ok[f] += 1
                    site_ok[site] += 1
            if v["invented"]:
                inv[f] += 1
    all_ok, all_tot = sum(ok.values()), sum(tot.values())
    secs = [r["sec"] for r in rows if not r["err"]]
    tin = [r["usage"].get("prompt_tokens") or 0 for r in rows if r["usage"]]
    tout = [r["usage"].get("completion_tokens") or 0 for r in rows if r["usage"]]
    pp = [r["timings"]["prompt_per_second"] for r in rows if r.get("timings")]
    tg = [r["timings"]["predicted_per_second"] for r in rows if r.get("timings")]
    print(f"\n=== {path}  (запросов {len(rows)}, ошибок {sum(1 for r in rows if r['err'])}, "
          f"JSON разобран {sum(r['json_ok'] for r in rows)})")
    print(f"ИТОГО по видимым полям: {all_ok}/{all_tot} = {all_ok / max(all_tot, 1):.1%}")
    for f in FIELDS:
        if tot[f]:
            print(f"  {f:13} {ok[f]:>3}/{tot[f]:<3} {ok[f] / tot[f]:6.1%}   выдумано {inv[f]}")
    for s in site_tot:
        print(f"  [{s}] {site_ok[s]}/{site_tot[s]} = {site_ok[s] / site_tot[s]:.1%}")
    if secs:
        print(f"секунд на страницу: медиана {st.median(secs):.1f}, p90 {sorted(secs)[int(0.9 * (len(secs) - 1))]:.1f}")
    if tin:
        print(f"токенов входа: медиана {st.median(tin):.0f}, макс {max(tin)}; выхода: медиана {st.median(tout):.0f}")
    if pp:
        print(f"llama.cpp: чтение {st.median(pp):.0f} ток/с, ответ {st.median(tg):.1f} ток/с (медианы)")
    return rows


if __name__ == "__main__":
    for p in sys.argv[1:]:
        summarize(p)
