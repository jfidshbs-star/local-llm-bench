"""Замер задержки MCP «от вызова до ответа»: клиент → HTTP → сервер → Postgres → JSON обратно.

Одна сессия, прогрев, затем N вызовов каждого инструмента с разными аргументами.
Плюс нагрузка: C параллельных клиентов. Печатает p50/p95/p99/макс в миллисекундах
и раскладку серверного времени (эмбеддинг запроса / SQL) из timing_ms.

Запуск: .venv/bin/python mcp_latency.py --n 200 --conc 8
"""
import argparse
import asyncio
import json
import random
import statistics as st
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mcp import Client

URL = "http://127.0.0.1:8765/mcp"
HERE = Path(__file__).parent
QUERIES = ["беспроводные наушники", "диван угловой серый", "матрас жёсткий 160 на 200", "велосипедный звонок",
           "смарт-часы для бега", "шкаф-купе", "кровать с подъёмным механизмом", "фонарь на руль", "xiaomi",
           "детский велосипед", "подушка ортопедическая", "кресло для отдыха", "garmin", "насос для велосипеда"]


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def summary(name, lat, server):
    s = {"tool": name, "n": len(lat), "p50": round(pct(lat, 50), 1), "p95": round(pct(lat, 95), 1),
         "p99": round(pct(lat, 99), 1), "max": round(max(lat), 1)}
    for k in (server[0].keys() if server else []):
        s[f"server_{k}_p50"] = round(st.median(x[k] for x in server), 2)
    print(json.dumps(s, ensure_ascii=False))
    return s


def args_for(tool, ids):
    if tool == "search":
        return {"query": random.choice(QUERIES), "limit": 5}
    if tool == "get_record":
        return {"id": random.choice(ids)}
    return {"since": (datetime.now(timezone.utc) - timedelta(minutes=random.randint(5, 600))).isoformat(), "limit": 50}


async def one_client(tool, n, ids, lat, server):
    async with Client(URL) as c:
        for _ in range(3):
            await c.call_tool(tool, args_for(tool, ids))
        for _ in range(n):
            t0 = time.perf_counter()
            r = await c.call_tool(tool, args_for(tool, ids))
            lat.append((time.perf_counter() - t0) * 1000)
            body = r.structured_content or (json.loads(r.content[0].text) if r.content else {})
            server.append(body.get("timing_ms", {}))


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--conc", type=int, default=8)
    a = ap.parse_args()
    random.seed(1)
    ids = [json.loads(l)["id"] for l in open(HERE / "corpus" / "gold.jsonl")] + [f"syn/{i}" for i in range(0, 20000, 7)]
    out = []
    # холодный вызов: новое соединение + первый запрос
    t0 = time.perf_counter()
    async with Client(URL) as c:
        await c.call_tool("get_record", {"id": ids[0]})
    cold = (time.perf_counter() - t0) * 1000
    print(json.dumps({"cold_connect_and_first_call_ms": round(cold, 1)}))
    for tool in ("get_record", "changed_since", "search"):
        lat, server = [], []
        await one_client(tool, a.n, ids, lat, server)
        out.append(summary(tool, lat, server))
    # нагрузка: conc клиентов одновременно, поиск (самый тяжёлый)
    lat, server = [], []
    t0 = time.perf_counter()
    await asyncio.gather(*[one_client("search", a.n // 4, ids, lat, server) for _ in range(a.conc)])
    wall = time.perf_counter() - t0
    s = summary(f"search x{a.conc} параллельно", lat, server)
    s["rps"] = round(len(lat) / wall, 1)
    out.append(s)
    print("rps", s["rps"])
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "mcp-latency.json").write_text(json.dumps({"cold_ms": round(cold, 1), "tools": out},
                                                                    ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
