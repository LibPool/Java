#!/usr/bin/env python3
"""Download the complete Maven Central artifact catalog with resumable pages."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import random
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path


ENDPOINT = "https://search.maven.org/solrsearch/select"
USER_AGENT = "LibPool-Indexer/1.0 (+https://github.com/LibPool)"
FIELDS = "id,g,a,latestVersion,versionCount,p,ec,timestamp"


def fetch_page(start: int, rows: int, retries: int) -> tuple[int, int, list[dict]]:
    params = urllib.parse.urlencode({
        "q": "*:*", "rows": rows, "start": start, "wt": "json", "fl": FIELDS,
    })
    url = f"{ENDPOINT}?{params}"
    error: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.load(response)
            result = data["response"]
            docs = result.get("docs", [])
            if not isinstance(docs, list) or (result.get("numFound", 0) and not docs):
                raise ValueError(f"empty/invalid page at start={start}")
            normalized = []
            for doc in docs:
                group, artifact = doc.get("g"), doc.get("a")
                if not group or not artifact:
                    continue
                normalized.append({
                    "group": group,
                    "artifact": artifact,
                    "latest": doc.get("latestVersion", ""),
                    "version_count": doc.get("versionCount", 0),
                    "packaging": doc.get("p", ""),
                    "timestamp": doc.get("timestamp", 0),
                    "extensions": doc.get("ec", []),
                })
            return start, int(result["numFound"]), normalized
        except Exception as exc:
            error = exc
            time.sleep(min(30, 1.5 ** attempt) + random.random())
    raise RuntimeError(f"page start={start} failed after {retries} attempts: {error}")


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, separators=(",", ":"))
            stream.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("tools/cache/maven_catalog.json"))
    parser.add_argument("--rows", type=int, default=200)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--retries", type=int, default=6)
    parser.add_argument("--max-pages", type=int, default=0, help="0 means fetch all remaining pages")
    args = parser.parse_args()
    if not 1 <= args.rows <= 200:
        parser.error("--rows must be between 1 and 200 (Maven Search caps larger pages)")
    if args.workers < 1:
        parser.error("--workers must be positive")

    catalog: dict[str, dict] = {}
    completed: set[int] = set()
    expected_total: int | None = None
    if args.out.exists():
        state = json.loads(args.out.read_text(encoding="utf-8"))
        if state.get("query") == "*:*" and state.get("rows") == args.rows:
            expected_total = state.get("num_found")
            completed = set(state.get("completed_starts", []))
            catalog = state.get("artifacts", {})
            print(f"Resuming: {len(catalog)} coordinates, {len(completed)} pages", flush=True)

    # Probe the live result count so paging remains auditable if the catalog changes.
    _, live_total, probe = fetch_page(0, args.rows, args.retries)
    if expected_total is not None and expected_total != live_total:
        print(f"Catalog count changed: {expected_total} -> {live_total}; retaining completed pages", flush=True)
    expected_total = live_total
    starts = list(range(0, expected_total, args.rows))
    missing = [start for start in starts if start not in completed]
    if args.max_pages:
        missing = missing[:args.max_pages]
    print(f"Maven Central reports {expected_total:,} coordinates; {len(missing):,} pages pending", flush=True)

    # Preserve and checkpoint successful pages. Failed pages remain absent and are retried
    # on the next run; each checkpoint is atomically replaced so interruption is recoverable.
    if 0 not in completed:
        for doc in probe:
            catalog[f"{doc['group']}:{doc['artifact']}"] = doc
        completed.add(0)
    pending_futures: dict[concurrent.futures.Future, int] = {}
    done_since_checkpoint = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        iterator = iter(start for start in missing if start != 0)
        for start in iterator:
            pending_futures[executor.submit(fetch_page, start, args.rows, args.retries)] = start
            if len(pending_futures) < args.workers * 2:
                continue
            finished, _ = concurrent.futures.wait(
                pending_futures, return_when=concurrent.futures.FIRST_COMPLETED
            )
            for future in finished:
                requested = pending_futures.pop(future)
                start, count, docs = future.result()
                if count != expected_total:
                    raise RuntimeError(f"result count changed during crawl: {expected_total} -> {count}")
                if start != requested:
                    raise RuntimeError(f"page mismatch: requested {requested}, got {start}")
                for doc in docs:
                    catalog[f"{doc['group']}:{doc['artifact']}"] = doc
                completed.add(start)
                done_since_checkpoint += 1
            if done_since_checkpoint >= 20:
                atomic_json(args.out, {
                    "query": "*:*", "rows": args.rows, "num_found": expected_total,
                    "completed_starts": sorted(completed), "artifacts": catalog,
                })
                print(f"Checkpoint: {len(completed):,}/{len(starts):,} pages, {len(catalog):,} unique coordinates", flush=True)
                done_since_checkpoint = 0
        for future, requested in list(pending_futures.items()):
            start, count, docs = future.result()
            if count != expected_total or start != requested:
                raise RuntimeError(f"inconsistent final page at start={requested}")
            for doc in docs:
                catalog[f"{doc['group']}:{doc['artifact']}"] = doc
            completed.add(start)

    atomic_json(args.out, {
        "query": "*:*", "rows": args.rows, "num_found": expected_total,
        "completed_starts": sorted(completed), "artifacts": catalog,
    })
    print(
        f"Saved {len(catalog):,}/{expected_total:,} unique coordinates; "
        f"{len(completed):,}/{len(starts):,} pages complete to {args.out}",
        flush=True,
    )
    return 0 if len(completed) == len(starts) and len(catalog) == expected_total else 2


if __name__ == "__main__":
    raise SystemExit(main())
