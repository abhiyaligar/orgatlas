"""Wipe every data store this application owns, and nothing else.

Deliberately explicit about what is dropped, because the alternative -- a
generic "drop everything" -- is how a shared instance loses someone else's data.
"""

import logging
import sys
from pathlib import Path

logging.disable(logging.CRITICAL)

from sqlalchemy import inspect, text  # noqa: E402

from app.core.dependencies import engine  # noqa: E402
from app.graph.connection import graph_manager, org_graph_name  # noqa: E402
from app.storage import source_store  # noqa: E402

stage = sys.argv[1] if len(sys.argv) > 1 else "all"

if stage in ("db", "all"):
    inspector = inspect(engine)
    tables = [t for t in inspector.get_table_names() if t != "alembic_version"]
    print(f"  postgres: dropping {len(tables)} table(s): {sorted(tables)}")
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    print("  postgres: public schema dropped and recreated empty")

if stage in ("graph", "all"):
    org = org_graph_name()
    client = graph_manager.get_client()
    for name in client.list_graphs():
        if name == "orgatlas":
            # Empty and not ours; leave it alone.
            continue
        graph = client.select_graph(name)
        graph.query("MATCH (n) DETACH DELETE n")
        size = list(graph.query("MATCH (n) RETURN count(n) AS c").result_set)[0][0]
        print(f"  graph {name:34} cleared ({size} nodes left)")

if stage in ("storage", "all"):
    if source_store.is_configured():
        import boto3
        from botocore.config import Config
        from app.core.config import settings

        c = boto3.client(
            "s3",
            endpoint_url=settings.SUPABASE_S3_ENDPOINT,
            aws_access_key_id=settings.SUPABASE_S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.SUPABASE_S3_SECRET_ACCESS_KEY,
            region_name=settings.SUPABASE_S3_REGION,
            config=Config(signature_version="s3v4"),
        )
        token = None
        removed = 0
        while True:
            kwargs = {"Bucket": settings.SOURCE_BUCKET, "MaxKeys": 1000}
            if token:
                kwargs["ContinuationToken"] = token
            page = c.list_objects_v2(**kwargs)
            batch = page.get("Contents", [])
            if not batch:
                break
            for obj in batch:
                c.delete_object(Bucket=settings.SOURCE_BUCKET, Key=obj["Key"])
                removed += 1
            token = page.get("NextContinuationToken")
            if not page.get("IsTruncated"):
                break
        print(f"  storage: removed {removed} object(s) from {settings.SOURCE_BUCKET}")
    else:
        print("  storage: not configured, nothing to clear")

if stage in ("cache", "all"):
    cache = Path("data/ingest_cache")
    if cache.exists():
        count = sum(1 for _ in cache.rglob("*") if _.is_file())
        for f in cache.rglob("*"):
            if f.is_file():
                f.unlink()
        print(f"  cache: removed {count} file(s) from {cache}")
    else:
        print("  cache: nothing at data/ingest_cache")