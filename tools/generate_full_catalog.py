#!/usr/bin/env python3
"""Generate the full LibPool Java index from the Maven Central catalog dump.

The crawl tool downloads the complete Maven Central coordinate list; this
script renders one markdown page per artifact, reusing the richer metadata
cache when available and falling back to a conservative stub otherwise.  It is
resumable and only writes missing files.

Layout:
  java-v<major>/<group-path>/<artifact>.md

Run from the repo root:
    python tools/generate_full_catalog.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "tools" / "cache" / "maven_catalog.json"
META_PATH = ROOT / "tools" / "cache" / "java_meta.json"
STATE_PATH = ROOT / "tools" / "cache" / "java_full_state.json"
MAVEN_REPO = "https://repo.maven.apache.org/maven2"
JAVA_RELEASES = ["java-v8", "java-v11", "java-v17", "java-v21", "java-v25", "java-v26"]


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_state() -> set[str]:
    if not STATE_PATH.exists():
        return set()
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return set(data.get("generated", []))
    except Exception:
        return set()


def save_state(generated: set[str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated": sorted(generated),
        "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def safe_artifact(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._+-]", "-", name)


def baseline_from_catalog(doc: dict) -> str:
    """Conservative Java baseline without fetched metadata."""
    version_count = int(doc.get("version_count") or 0)
    timestamp = int(doc.get("timestamp") or 0)
    if timestamp:
        year = time.gmtime(timestamp / 1000).tm_year
        if year <= 2018:
            return "java-v8"
        if year <= 2021:
            return "java-v11"
        return "java-v17"
    if version_count and version_count >= 12:
        return "java-v17"
    return "java-v8"


def readme_md(group: str, artifact: str, meta: dict | None) -> str:
    coords = f"{group}:{artifact}"
    repo_base = f"{MAVEN_REPO}/{group.replace('.', '/')}/{artifact}"
    latest = (meta or {}).get("latest") or ""
    versions = (meta or {}).get("versions") or []
    description = (meta or {}).get("description") or f"{artifact} - Java library from Maven Central"
    homepage = (meta or {}).get("homepage") or ""
    scm_url = (meta or {}).get("scm_url") or ""
    tags = (meta or {}).get("tags") or []
    java_targets = (meta or {}).get("java_targets") or []

    if versions:
        version_lines = "\n".join(f"- {v}" for v in versions[-10:])
        if len(versions) > 10:
            version_lines += f"\n- 共 {len(versions)} 个版本，完整清单见 Maven Central。"
    else:
        version_lines = "- 未知"

    baseline = java_targets[0] if java_targets else baseline_from_catalog(doc_for(coords))
    expanded = [d for d in JAVA_RELEASES if int(d.replace("java-v", "")) >= int(baseline.replace("java-v", ""))]
    website = homepage if homepage.startswith("http") else f"https://central.sonatype.com/artifact/{urllib.parse.quote(coords)}"
    downloads = [
        f"- Maven 仓库地址：{repo_base}/",
        f"- Maven 坐标：`{coords}`",
    ]
    if latest:
        downloads.append(
            f"- pom.xml 引用：`<dependency><groupId>{group}</groupId><artifactId>{artifact}</artifactId><version>{latest}</version></dependency>`"
        )
    if scm_url.startswith("http"):
        downloads.append(f"- 源码仓库：{scm_url}")
    tag_line = ", ".join(sorted(set(tags))) if tags else "Java"
    if not any(t.startswith("Java ") for t in tags):
        tag_line += f", Java {baseline.replace('java-v', '')}+"
    compat_note = f"最低 Java 版本：Java {baseline.replace('java-v', '')}；已收录于 {', '.join(expanded)}。"
    return f"""# {artifact}

> 标签: {tag_line}

## 简介

{description}

{compat_note}

## 官网

- {website}

## 历史版本号

{version_lines}

## 获取地址

{chr(10).join(downloads)}
"""


# Late-bound catalog document used by the stub baseline helper.
_CATALOG: dict = {}


def doc_for(coords: str) -> dict:
    return _CATALOG.get(coords) or {}


def count_editions() -> dict[str, int]:
    counts = {release: 0 for release in JAVA_RELEASES}
    for release in JAVA_RELEASES:
        release_dir = ROOT / release
        if not release_dir.exists():
            continue
        for entry in release_dir.iterdir():
            if entry.is_dir() and not entry.name.startswith("."):
                counts[release] += 1
    return counts


def write_java_readme(counts: dict[str, int], total: int) -> None:
    lines = [
        "# Java 库索引",
        "",
        "本目录收录来自 Maven Central 的 Java 库索引，按 Java 大版本与 Maven groupId 包路径组织：",
        "",
        "- 大版本目录：`java-v8`、`java-v11`、`java-v17`、`java-v21`、`java-v25`、`java-v26`",
        "- 包路径：`groupId` 中的 `.` 转成目录分隔符，例如 `org.springframework:spring-context` 位于 `org/springframework/spring-context.md`",
        "- 库若兼容多个 Java 大版本，会同时出现在所有后续版本目录中",
        "",
        f"当前共收录 {total:,} 个 Maven 坐标（来源为 Maven Central 搜索 API 全量分页）：",
        "",
    ]
    lines += [f"- {k}：{v:,} 个库" for k, v in counts.items()]
    lines += [
        "",
        "## 数据源",
        "",
        "- Maven Central：https://repo.maven.apache.org/maven2/",
        "- Maven Central 搜索：https://search.maven.org/",
        "- 中央仓库主页：https://central.sonatype.com/",
        "",
        "## 生成方式",
        "",
        "```bash",
        "python tools/crawl_catalog.py",
        "python tools/generate_full_catalog.py",
        "```",
        "",
    ]
    (ROOT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT)
    parser.add_argument("--max-artifacts", type=int, default=0)
    parser.add_argument("--checkpoint-every", type=int, default=2000)
    args = parser.parse_args()

    catalog = load_json(CATALOG_PATH)
    artifacts = catalog.get("artifacts") or {}
    if not artifacts:
        print(f"catalog missing or empty: {CATALOG_PATH}", file=sys.stderr)
        return 1
    print(f"Catalog: {len(artifacts):,} Maven coordinates", flush=True)
    _CATALOG.update(artifacts)
    meta = load_json(META_PATH)
    generated = load_state()
    pending = [key for key in sorted(artifacts) if key not in generated]
    if args.max_artifacts:
        pending = pending[: args.max_artifacts]
    print(f"Pending: {len(pending):,} artifacts", flush=True)

    done = 0
    for coords in pending:
        group, artifact = coords.split(":", 1)
        lib_meta = meta.get(coords)
        text = readme_md(group, artifact, lib_meta)
        baseline = baseline_from_catalog(artifacts[coords])
        if lib_meta and lib_meta.get("java_targets"):
            baseline = lib_meta["java_targets"][0]
        min_major = int(baseline.replace("java-v", ""))
        releases = [d for d in JAVA_RELEASES if int(d.replace("java-v", "")) >= min_major]
        package_path = group.replace(".", "/")
        safe = safe_artifact(artifact)
        for release in releases:
            target = args.out / release / package_path
            try:
                target.mkdir(parents=True, exist_ok=True)
                md = target / f"{safe}.md"
                if not md.exists():
                    md.write_text(text, encoding="utf-8")
            except Exception as exc:
                print(f"  write error {target}: {exc}", flush=True)
        generated.add(coords)
        done += 1
        if done % args.checkpoint_every == 0:
            save_state(generated)
            print(f"  generated {done:,}/{len(pending):,}", flush=True)

    save_state(generated)
    counts = count_editions()
    if not args.max_artifacts:
        write_java_readme(counts, len(generated))
    print("Edition counts:", json.dumps(counts, sort_keys=True), flush=True)
    print(f"Done: {len(generated):,} artifacts", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
