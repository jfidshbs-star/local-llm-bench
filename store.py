"""База собранных записей под вопрос 2: Postgres + pgvector, гибридный поиск.

Таблица records: поля товара (jsonb), текст, источник, дата проверки, ETag и хэш
содержимого (свежесть: неизменённое при обходе не перезаписываем), полнотекст
(tsvector, русский словарь) и эмбеддинг 384 (multilingual MiniLM на CPU, fastembed).

Нагрузка: к 50 настоящим карточкам добавляем N синтетических записей (варианты
настоящих названий), чтобы мерить задержку на таблице реального размера.
В отчёте они так и названы — синтетика для нагрузки, не собранные данные.

Запуск: .venv/bin/python store.py --synthetic 20000   (CPU нашего сервера: ~34 эмбеддинга/с)
"""
import argparse
import hashlib
import json
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import psycopg
from fastembed import TextEmbedding

HERE = Path(__file__).parent
DSN = "postgresql://postgres:test@127.0.0.1:55432/sbor"
EMB_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

DDL = """
drop table if exists records;
create table records (
  id           text primary key,
  source       text not null,
  url          text not null,
  checked_at   timestamptz not null,
  changed_at   timestamptz not null,
  etag         text,
  content_hash text not null,
  fields       jsonb not null,
  body         text not null,
  tsv          tsvector generated always as (to_tsvector('russian', coalesce(fields->>'name','') || ' ' || body)) stored,
  emb          vector(384) not null,
  synthetic    boolean not null default false
);
"""
INDEXES = """
create index records_tsv on records using gin (tsv);
create index records_emb on records using hnsw (emb vector_cosine_ops);
create index records_changed on records (changed_at);
analyze records;
"""

VARIANTS = ["", " комплект 2 шт.", " уценка", " новая версия", " цвет чёрный", " цвет белый", " большой размер",
            " малый размер", " для дома", " профессиональный", " набор", " 2026", " мини", " про", " лайт"]


def emb_text(fields, body):
    return (fields.get("name") or "") + ". " + (fields.get("brand") or "") + ". " + body[:500]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", type=int, default=20000)
    a = ap.parse_args()
    gold = [json.loads(l) for l in open(HERE / "corpus" / "gold.jsonl", encoding="utf-8")]
    # сервер общий с ботом: 2 потока и маленькие пачки, иначе onnxruntime берёт 1,7 ГБ
    model = TextEmbedding(model_name=EMB_MODEL, threads=2)
    now = datetime.now(timezone.utc)

    rows = []
    for g in gold:
        text = (HERE / "corpus" / "text" / f"{g['id']}.txt").read_text(encoding="utf-8")
        body = text[:2000]
        rows.append((g["id"], g["id"].split("/")[0], g["url"], now, now, None,
                     hashlib.sha256(text.encode()).hexdigest(), g["gold"], body, False))
    random.seed(7)
    for i in range(a.synthetic):
        base = random.choice(gold)
        f = dict(base["gold"])
        f["name"] = (f["name"] or "") + random.choice(VARIANTS)
        if f.get("price"):
            f["price"] = round(f["price"] * random.uniform(0.7, 1.3))
        ts = now - timedelta(minutes=random.randint(0, 60 * 24 * 14))
        body = f["name"] + ". " + (f.get("brand") or "")
        rows.append((f"syn/{i}", "synthetic", base["url"] + f"#syn{i}", ts, ts, None,
                     hashlib.sha256(body.encode()).hexdigest(), f, body, True))

    t0 = time.perf_counter()
    vecs = list(model.embed([emb_text(r[7], r[8]) for r in rows], batch_size=16))
    t_emb = time.perf_counter() - t0
    print(f"эмбеддинги: {len(vecs)} за {t_emb:.1f} с ({len(vecs) / t_emb:.0f} шт/с на CPU)")

    with psycopg.connect(DSN, autocommit=True) as con:
        con.execute(DDL)
        t0 = time.perf_counter()
        with con.cursor() as cur:
            with cur.copy("copy records (id, source, url, checked_at, changed_at, etag, content_hash, fields, body, synthetic, emb) from stdin") as cp:
                for r, v in zip(rows, vecs):
                    cp.write_row(list(r[:7]) + [json.dumps(r[7], ensure_ascii=False), r[8], r[9],
                                                "[" + ",".join(f"{x:.6f}" for x in np.asarray(v)) + "]"])
        t_load = time.perf_counter() - t0
        t0 = time.perf_counter()
        con.execute(INDEXES)
        t_idx = time.perf_counter() - t0
        n = con.execute("select count(*) from records").fetchone()[0]
        size = con.execute("select pg_size_pretty(pg_total_relation_size('records'))").fetchone()[0]
    print(f"загрузка {t_load:.1f} с, индексы {t_idx:.1f} с, записей {n}, объём {size}")


if __name__ == "__main__":
    main()
