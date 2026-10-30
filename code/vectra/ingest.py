"""Ingestion: embed the current, reviewed articles and upsert them to Pinecone (one vector each).

Re-running is safe: vector id = doc_id, so an article is overwritten, and any article that is no
longer 'current' (e.g. KB-002 after KB-007 replaced it) is deleted from the index.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from .config import (EMBED_DIM, EMBED_MODEL, MANIFEST_PATH, OPENAI_API_KEY, PINECONE_API_KEY,
                     PINECONE_CLOUD, PINECONE_INDEX, PINECONE_REGION)
from .knowledge_base import Article, ingest_decision, kb_version, load_articles


def vector_metadata(a: Article) -> dict:
    meta = {
        "doc_id": a.doc_id,
        "title": a.title,
        "status": a.status,
        "effective_date": a.effective_date,
        "owner": a.meta.get("owner"),
        "supersedes": a.meta.get("supersedes"),
        "text": a.text,          # stored so a search returns the article without a second lookup
    }
    return {k: v for k, v in meta.items() if v is not None}   # Pinecone rejects null metadata


def ensure_index(pc) -> None:
    from pinecone import ServerlessSpec
    if not pc.has_index(PINECONE_INDEX):
        print(f"Creating Pinecone index '{PINECONE_INDEX}' ({EMBED_DIM} dims, cosine)...")
        pc.create_index(name=PINECONE_INDEX, dimension=EMBED_DIM, metric="cosine",
                        spec=ServerlessSpec(cloud=PINECONE_CLOUD, region=PINECONE_REGION))


def ingest(dry_run: bool = False) -> None:
    articles = load_articles()
    decisions = [(a, *ingest_decision(a)) for a in articles]
    keep = [a for a, ok, _ in decisions if ok]
    drop = [(a, why) for a, ok, why in decisions if not ok]

    print(f"{'doc_id':<8} {'status':<11} {'chars':>5}  {'decision':<8} reason")
    for a, ok, why in decisions:
        print(f"{a.doc_id:<8} {a.status:<11} {len(a.text):>5}  {'INGEST' if ok else 'SKIP':<8} {why}")
    print(f"\n{len(keep)} articles -> {len(keep)} vectors (one per article, tables kept whole)")
    if dry_run:
        return

    from openai import OpenAI
    from pinecone import Pinecone

    pc = Pinecone(api_key=PINECONE_API_KEY)
    ensure_index(pc)
    index = pc.Index(PINECONE_INDEX)

    client = OpenAI(api_key=OPENAI_API_KEY)
    resp = client.embeddings.create(model=EMBED_MODEL, input=[a.text for a in keep])  # one batched call
    index.upsert(vectors=[{"id": a.doc_id, "values": d.embedding, "metadata": vector_metadata(a)}
                          for a, d in zip(keep, resp.data)])
    if drop:
        index.delete(ids=[a.doc_id for a, _ in drop])   # retire anything that is no longer current

    # Serverless indexes are eventually consistent; wait until the count matches.
    for _ in range(30):
        count = index.describe_index_stats().total_vector_count
        if count == len(keep):
            break
        time.sleep(1)
    print(f"Index '{PINECONE_INDEX}' now holds {count} vectors.")

    manifest = {
        "kb_version": kb_version(keep),
        "ingested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "index": PINECONE_INDEX,
        "embed_model": EMBED_MODEL,
        "ingested": [{"doc_id": a.doc_id, "title": a.title, "effective_date": a.effective_date} for a in keep],
        "skipped": [{"doc_id": a.doc_id, "status": a.status, "reason": why} for a, why in drop],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {MANIFEST_PATH.name} (kb_version {manifest['kb_version']}).")
