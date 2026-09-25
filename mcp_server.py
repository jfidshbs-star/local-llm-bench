"""Узкий MCP-сервер над базой собранных записей (вопрос 2: «свежие данные быстрее секунды»).

LLM на пути запроса нет: записи уже лежат в Postgres, инструмент — это запрос к базе.
Три инструмента: search (гибрид: полнотекст + векторы, слияние RRF), get_record, changed_since.
Каждый ответ несёт источник и дату проверки — модель видит возраст факта.
В ответ кладём timing_ms (эмбеддинг запроса / SQL), чтобы разложить задержку.

Слушает только 127.0.0.1 — «закрыт снаружи». Наружу — через туннель с токеном, не портом.
Запуск: .venv/bin/python mcp_server.py   → http://127.0.0.1:8765/mcp
"""
import time

import numpy as np
from fastembed import TextEmbedding
from mcp.server import MCPServer
from psycopg_pool import ConnectionPool

from store import DSN, EMB_MODEL

pool = ConnectionPool(DSN, min_size=2, max_size=8, kwargs={"autocommit": True}, open=True)
model = TextEmbedding(model_name=EMB_MODEL)
list(model.query_embed("прогрев"))  # первая инференция медленная — греем при старте

mcp = MCPServer("sbor", instructions="Собранные карточки товаров: поиск, запись по id, изменения с даты.")

COLS = "id, source, url, checked_at, fields->>'name', (fields->>'price')::float, fields->>'currency', fields->>'availability'"


def row(r):
    return {"id": r[0], "source": r[1], "url": r[2], "checked_at": r[3].isoformat(timespec="seconds"),
            "name": r[4], "price": r[5], "currency": r[6], "availability": r[7]}


@mcp.tool()
def search(query: str, limit: int = 5) -> dict:
    """Найти товары по смыслу и по словам. Возвращает до limit записей с источником и датой проверки."""
    t0 = time.perf_counter()
    q = np.asarray(next(iter(model.query_embed(query))))
    vec = "[" + ",".join(f"{x:.6f}" for x in q) + "]"
    t1 = time.perf_counter()
    sql = f"""
    with fts as (
      select id, row_number() over (order by ts_rank(tsv, websearch_to_tsquery('russian', %(q)s)) desc) rk
      from records where tsv @@ websearch_to_tsquery('russian', %(q)s) limit 20),
    vec as (
      select id, row_number() over (order by emb <=> %(v)s::vector) rk
      from (select id, emb from records order by emb <=> %(v)s::vector limit 20) s),
    fused as (
      select id, sum(1.0 / (60 + rk)) score from (select * from fts union all select * from vec) u
      group by id order by score desc limit %(k)s)
    select {COLS} from fused join records using (id) order by fused.score desc"""
    with pool.connection() as con:
        rows = con.execute(sql, {"q": query, "v": vec, "k": max(1, min(limit, 20))}).fetchall()
    t2 = time.perf_counter()
    return {"results": [row(r) for r in rows],
            "timing_ms": {"embed": round((t1 - t0) * 1000, 2), "sql": round((t2 - t1) * 1000, 2)}}


@mcp.tool()
def get_record(id: str) -> dict:
    """Запись целиком по id: поля товара, источник, дата проверки."""
    t0 = time.perf_counter()
    with pool.connection() as con:
        r = con.execute("select id, source, url, checked_at, fields from records where id = %s", (id,)).fetchone()
    t1 = time.perf_counter()
    rec = None if r is None else {"id": r[0], "source": r[1], "url": r[2],
                                  "checked_at": r[3].isoformat(timespec="seconds"), "fields": r[4]}
    return {"record": rec, "timing_ms": {"sql": round((t1 - t0) * 1000, 2)}}


@mcp.tool()
def changed_since(since: str, limit: int = 50) -> dict:
    """Что изменилось после момента since (ISO 8601): новые цены, наличие, новые товары."""
    t0 = time.perf_counter()
    with pool.connection() as con:
        rows = con.execute(f"select {COLS} from records where changed_at > %s::timestamptz "
                           f"order by changed_at desc limit %s", (since, max(1, min(limit, 200)))).fetchall()
    t1 = time.perf_counter()
    return {"results": [row(r) for r in rows], "timing_ms": {"sql": round((t1 - t0) * 1000, 2)}}


if __name__ == "__main__":
    mcp.run("streamable-http", host="127.0.0.1", port=8765)
