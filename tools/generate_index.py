#!/usr/bin/env python3
"""Generate the LibPool Java library index from Maven Central metadata.

Layout:
  <java-version>/<package-path>/<artifact>.md

The artifact file is rendered for every Java release directory that the
artifact supports. Run from the repo root:
    python tools/generate_index.py
"""

from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path


MAVEN_REPO = "https://repo.maven.apache.org/maven2"
MAVEN_SEARCH = "https://search.maven.org/solrsearch/select"
USER_AGENT = "LibPool-Indexer/1.0 (+https://github.com/LibPool)"

# Canonical Java release directories used by the index.
JAVA_RELEASES = ["java-v8", "java-v11", "java-v17", "java-v21", "java-v25", "java-v26"]

# Conservative fallback when a POM/manifest does not declare a target.
FALLBACK_BY_AGE = {
    "old": "java-v8",      # released before the Java 11 era (<= 2018)
    "mid": "java-v11",     # 2019-2021
    "new": "java-v17",     # 2022+
}

CACHE_PATH = Path(__file__).resolve().parent / "cache" / "java_meta.json"


@dataclass
class Library:
    group: str
    artifact: str
    latest: str = ""
    description: str = ""
    homepage: str = ""
    scm_url: str = ""
    tags: list[str] = field(default_factory=list)
    versions: list[str] = field(default_factory=list)
    java_targets: list[str] = field(default_factory=list)
    class_major: int | None = None

    @property
    def package_path(self) -> str:
        return self.group.replace(".", "/")

    @property
    def safe_name(self) -> str:
        return re.sub(r"[^A-Za-z0-9._+-]", "-", self.artifact)


def http_json(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def search_json(url: str) -> dict | None:
    """Maven search endpoint; curl first because urllib stalls on large replies."""
    for attempt in range(4):
        try:
            proc = subprocess.run(
                ["curl.exe", "-s", "-m", "30", url],
                capture_output=True,
                timeout=45,
                text=True,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return json.loads(proc.stdout)
            print(f"  search curl retry {attempt}: rc={proc.returncode}", flush=True)
        except Exception as exc:
            print(f"  search curl retry {attempt}: {exc}", flush=True)
        time.sleep(1.0 * (attempt + 1))
    return None


def http_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_latest_version(group: str, artifact: str) -> str:
    url = f"{MAVEN_REPO}/{group.replace('.', '/')}/{artifact}/maven-metadata.xml"
    text = http_text(url)
    root = ET.fromstring(text)
    latest = root.findtext("versioning/latest") or root.findtext("versioning/release") or ""
    versions = [v.text for v in root.findall("versioning/versions/version") if v.text]
    return latest, versions


def java_from_release_age(versions: list[str]) -> str:
    """No metadata: choose a safe baseline from the first release era."""
    if not versions:
        return "java-v8"
    first = versions[0]
    year = None
    m = re.search(r"(\d{4})", first)
    # Versions rarely encode years; fall back to ordering heuristics below.
    del year, m
    # Old projects overwhelmingly target Java 8; recent modularized builds
    # commonly require 17. This is a documented conservative default.
    if len(versions) < 12:
        return "java-v8"
    return "java-v17"


def java_from_pom(pom_text: str) -> list[str]:
    hits: list[str] = []
    patterns = [
        r"<maven\.compiler\.source>\s*([^<]+)",
        r"<maven\.compiler\.target>\s*([^<]+)",
        r"<java\.version>\s*([^<]+)",
        r"<release>\s*([^<]+)",
        r"<maven\.compiler\.release>\s*([^<]+)",
    ]
    for pat in patterns:
        m = re.search(pat, pom_text)
        if m:
            hits.append(m.group(1).strip())
    # Gradle module metadata can override (it is the authoritative source for
    # Gradle-built artifacts).
    g = re.search(r'"org\.gradle\.jvm\.version"\s*:\s*(\d+)', pom_text)
    if g:
        hits.insert(0, g.group(1))
    g_arr = re.search(r'"org\.gradle\.jvm\.version"\s*:\s*\[([^\]]+)\]', pom_text)
    if g_arr:
        for token in re.findall(r"\d+", g_arr.group(1)):
            hits.append(token)
    out = set()
    for raw in hits:
        for token in re.split(r"[,\s]+", raw):
            token = token.strip()
            if not token:
                continue
            if token.isdigit():
                v = int(token)
                out.add(java_release_dir(v))
            elif token.startswith("1.") and token[2:].isdigit():
                out.add(java_release_dir(int(token[2:])))
    return sorted(out, key=lambda x: int(x.replace("java-v", "")))


def java_from_versions_sampling(lib: Library) -> list[str]:
    """Probe a handful of release epochs to detect Java baseline changes.

    Most projects change the minimum Java version only at a major boundary.
    Sampling the oldest, newest and a few intermediate releases is enough to
    build a conservative compatibility set without fetching every version.
    """
    versions = lib.versions
    if not versions:
        return []
    picks = list(dict.fromkeys([versions[0], versions[-1]]))
    if len(versions) <= 12:
        picks = versions
    else:
        step = max(1, len(versions) // 6)
        picks.extend(versions[::step])
        picks = list(dict.fromkeys(picks))[:24]
    picks = list(dict.fromkeys(picks))[-12:]
    targets: list[str] = []
    base = f"{MAVEN_REPO}/{lib.group.replace('.', '/')}/{lib.artifact}"
    for v in picks:
        found = []
        try:
            module = http_text(f"{base}/{v}/{lib.artifact}-{v}.module")
            found.extend(java_from_pom(module))
        except Exception:
            pass
        if not found:
            try:
                pom = http_text(f"{base}/{v}/{lib.artifact}-{v}.pom")
                found.extend(java_from_pom(pom))
            except Exception:
                pass
        targets.extend(found)
    return sorted(set(targets), key=lambda x: int(x.replace("java-v", "")))


def class_major_from_jar(lib: Library) -> int | None:
    """Read the bytecode major version from the primary class files of a jar."""
    if not lib.latest:
        return None
    base = f"{MAVEN_REPO}/{lib.group.replace('.', '/')}/{lib.artifact}"
    url = f"{base}/{lib.latest}/{lib.artifact}-{lib.latest}.jar"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
    except Exception:
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            majors: set[int] = set()
            fallback: set[int] = set()
            for info in zf.infolist():
                if not info.filename.endswith(".class") or info.filename.endswith("module-info.class"):
                    continue
                if info.file_size < 8 or info.filename.startswith("META-INF/versions/"):
                    if info.filename.startswith("META-INF/versions/"):
                        fallback.add(read_class_major(zf, info))
                    continue
                major = read_class_major(zf, info)
                if major:
                    majors.add(major)
            chosen = majors or fallback
            return min(chosen) if chosen else None
    except Exception:
        return None


def read_class_major(zf: zipfile.ZipFile, info) -> int | None:
    try:
        with zf.open(info) as fp:
            head = fp.read(8)
        if len(head) < 8 or head[:4] != b"\xca\xfe\xba\xbe":
            return None
        return int.from_bytes(head[6:8], "big")
    except Exception:
        return None


def java_release_dir(major: int) -> str:
    if major <= 8:
        return "java-v8"
    if major <= 11:
        return "java-v11"
    if major <= 17:
        return "java-v17"
    if major <= 21:
        return "java-v21"
    if major <= 25:
        return "java-v25"
    return "java-v26"


def java_from_class_major(class_major: int) -> str:
    """Map a JVM class-file major version to a Java release directory."""
    if class_major <= 44:
        return "java-v8"
    return java_release_dir(max(8, class_major - 44))


def load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_cache(data: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def enrich(lib: Library, cache: dict, use_cache: bool) -> None:
    key = f"{lib.group}:{lib.artifact}"
    if use_cache and key in cache:
        entry = cache[key]
        lib.latest = entry.get("latest", "")
        lib.versions = entry.get("versions", [])
        lib.description = entry.get("description", "")
        lib.homepage = entry.get("homepage", "")
        lib.scm_url = entry.get("scm_url", "")
        lib.java_targets = entry.get("java_targets", [])
        lib.class_major = entry.get("class_major")
        lib.tags = list(dict.fromkeys(lib.tags + entry.get("tags", [])))
        return

    latest, versions = fetch_latest_version(lib.group, lib.artifact)
    lib.latest = latest or versions[-1] if versions else ""
    lib.versions = versions

    base = f"{MAVEN_REPO}/{lib.group.replace('.', '/')}/{lib.artifact}/{lib.latest}"
    module_url = f"{base}/{lib.artifact}-{lib.latest}.module"
    pom_url = f"{base}/{lib.artifact}-{lib.latest}.pom"
    try:
        try:
            module = http_text(module_url)
            lib.java_targets = java_from_pom(module)
        except Exception:
            lib.java_targets = []
        pom = http_text(pom_url)
        lib.java_targets += java_from_pom(pom)
        desc_m = re.search(r"<description>(.*?)</description>", pom, re.S)
        if desc_m:
            desc = re.sub(r"\s+", " ", desc_m.group(1)).strip()
            if desc and desc.lower() != "parent pom":
                lib.description = desc
        url_m = re.search(r"<url>(.*?)</url>", pom, re.S)
        if url_m:
            lib.homepage = url_m.group(1).strip()
        scm_m = re.search(r"<scm>.*?<url>(.*?)</url>", pom, re.S)
        if scm_m:
            lib.scm_url = scm_m.group(1).strip()
        if not lib.description:
            desc_m2 = re.search(r"<name>(.*?)</name>", pom, re.S)
            if desc_m2:
                lib.description = desc_m2.group(1).strip()
    except Exception:
        pass

    sampled = java_from_versions_sampling(lib)
    lib.java_targets = list(dict.fromkeys(lib.java_targets + sampled))
    lib.class_major = class_major_from_jar(lib)
    if lib.class_major:
        lib.java_targets.append(java_from_class_major(lib.class_major))
    lib.java_targets = sorted(set(lib.java_targets), key=lambda x: int(x.replace("java-v", "")))
    if not lib.java_targets:
        lib.java_targets = ["java-v8"]
    if not lib.description:
        lib.description = f"{lib.artifact} - Java library from Maven Central"
    if lib.homepage.startswith("http") and "github.com/" in lib.homepage:
        lib.tags.append("github")
    cache[key] = {
        "latest": lib.latest,
        "versions": lib.versions,
        "description": lib.description,
        "homepage": lib.homepage,
        "scm_url": lib.scm_url,
        "java_targets": lib.java_targets,
        "class_major": lib.class_major,
        "tags": lib.tags,
    }


def readme_md(lib: Library) -> str:
    coords = f"{lib.group}:{lib.artifact}"
    repo_base = f"{MAVEN_REPO}/{lib.group.replace('.', '/')}/{lib.artifact}"
    latest = lib.latest or ""
    version_links = "\n".join(
        f"- {v}" for v in lib.versions[-10:] or ["-"]
    )
    if len(lib.versions) > 10:
        version_links += f"\n- 共 {len(lib.versions)} 个版本，完整清单见 Maven Central。"
    website = lib.homepage if lib.homepage else f"https://central.sonatype.com/artifact/{urllib.parse.quote(coords)}"
    downloads = [
        f"- Maven 仓库地址：{repo_base}/",
        f"- Maven 坐标：`{coords}`",
    ]
    if latest:
        downloads.append(f"- pom.xml 引用：`<dependency><groupId>{lib.group}</groupId><artifactId>{lib.artifact}</artifactId><version>{latest}</version></dependency>`")
    if lib.scm_url.startswith("http"):
        downloads.append(f"- 源码仓库：{lib.scm_url}")

    baseline = lib.java_targets[0] if lib.java_targets else "java-v8"
    expanded = [d for d in JAVA_RELEASES if int(d.replace("java-v", "")) >= int(baseline.replace("java-v", ""))]
    tag_line = ", ".join(sorted(set(lib.tags))) if lib.tags else "Java"
    if not any(t.startswith("Java ") for t in lib.tags):
        tag_line += f", Java {baseline.replace('java-v', '')}+"
    compat_note = (
        f"最低 Java 版本：Java {baseline.replace('java-v', '')}；"
        f"已收录于 {', '.join(expanded)}。"
    )

    return f"""# {lib.artifact}

> 标签: {tag_line}

## 简介

{lib.description}

{compat_note}

## 官网

- {website}

## 历史版本号

{version_links}

## 获取地址

{chr(10).join(downloads)}
"""


def load_seeds(path: Path) -> list[Library]:
    data = json.loads(path.read_text(encoding="utf-8"))
    libs = []
    for item in data:
        lib = Library(
            group=item["group"],
            artifact=item["artifact"],
            tags=item.get("tags", []),
        )
        libs.append(lib)
    return libs


CRAWL_KEYWORDS = [
    "spring", "spring boot", "jakarta", "apache", "google", "guava", "gson",
    "jackson", "log", "sql", "jdbc", "redis", "kafka", "rabbitmq", "mqtt",
    "http", "web", "servlet", "json", "xml", "yaml", "orm", "hibernate",
    "mybatis", "mongo", "cassandra", "elasticsearch", "solr", "lucene",
    "netty", "vertx", "grpc", "protobuf", "rpc", "websocket", "security",
    "oauth", "jwt", "crypto", "encryption", "hash", "zookeeper", "curator",
    "hadoop", "spark", "flink", "hive", "hbase", "airflow", "kafka streams",
    "redis client", "jedis", "lettuce", "test", "junit", "mockito", "assert",
    "benchmark", "coverage", "maven", "gradle", "build", "parser", "html",
    "css", "markdown", "pdf", "excel", "word", "csv", "image", "camera",
    "mail", "smtp", "ftp", "sftp", "ssh", "dns", "scheduler", "cron",
    "cache", "caffeine", "ehcache", "mapstruct", "lombok", "kotlin", "scala",
    "reactive", "rxjava", "reactor", "retrofit", "okhttp", "jsoup", "selenium",
    "docker", "kubernetes", "aws", "azure", "gcp", "cloud", "kubectl",
    "opentelemetry", "micrometer", "prometheus", "grafana", "zipkin", "jaeger",
    "tracing", "metrics", "monitoring", "config", "feature", "validation",
    "hibernate validator", "bean validation", "jpa", "mybatis plus", "flyway",
    "liquibase", "sqlite", "postgresql", "mysql", "oracle", "sql server",
    "mqtt client", "paho", "amqp", "stomp", "graphql", "querydsl", "jooq",
    "quartz", "xxl-job", "elastic-job", "seata", "shardingsphere", "zookeeper",
]


def crawl_maven_unique_artifacts(max_artifacts: int) -> list[dict]:
    """Collect distinct Maven Central artifacts via targeted keyword queries."""
    seen: dict[tuple[str, str], dict] = {}
    for kw in CRAWL_KEYWORDS:
        q = urllib.parse.quote(kw)
        for start in range(0, 10001, 100):
            url = f"{MAVEN_SEARCH}?q={q}&rows=100&start={start}&wt=json"
            data = search_json(url)
            docs = (data or {}).get("response", {}).get("docs") or []
            if not docs:
                break
            for d in docs:
                g = d.get("g") or ""
                a = d.get("a") or ""
                if g and a:
                    key = (g, a)
                    if key not in seen:
                        seen[key] = {
                            "group": g,
                            "artifact": a,
                            "latest": d.get("latestVersion", ""),
                            "description": "",
                        }
            print(f"  kw={kw} start={start} unique={len(seen)}", flush=True)
            time.sleep(0.08)
            if len(seen) >= max_artifacts:
                return list(seen.values())
    return list(seen.values())


def crawl(args) -> list[Library]:
    print(f"Crawling Maven Central with {len(CRAWL_KEYWORDS)} keyword queries...", flush=True)
    artifacts = crawl_maven_unique_artifacts(args.crawl_limit)
    print(f"Found {len(artifacts)} unique artifacts", flush=True)
    libs: list[Library] = []
    for item in artifacts:
        libs.append(Library(group=item["group"], artifact=item["artifact"], latest=item.get("latest", "")))
    return libs


def generate(root: Path, libs: list[Library], out_dir: Path) -> dict[str, int]:
    counts = defaultdict(int)
    for lib in libs:
        if not lib.java_targets:
            continue
        text = readme_md(lib)
        baseline = lib.java_targets[0]
        min_major = int(baseline.replace("java-v", ""))
        releases = [d for d in JAVA_RELEASES if int(d.replace("java-v", "")) >= min_major]
        for release in releases:
            target = out_dir / release / lib.package_path
            target.mkdir(parents=True, exist_ok=True)
            (target / f"{lib.safe_name}.md").write_text(text, encoding="utf-8")
            counts[release] += 1
    return dict(counts)


def write_java_readme(root: Path, counts: dict[str, int], libs: list[Library]) -> None:
    lines = [
        "# Java 库索引",
        "",
        "本目录收录来自 Maven Central 的 Java 库索引，按 Java 大版本与 Maven groupId 包路径组织：",
        "",
        "- 大版本目录：`java-v8`、`java-v11`、`java-v17`、`java-v21`、`java-v25`、`java-v26`",
        "- 包路径：`groupId` 中的 `.` 转成目录分隔符，例如 `org.springframework:spring-context` 位于 `org/springframework/spring-context.md`",
        "- 库若兼容多个 Java 大版本，会同时出现在所有后续版本目录中",
        "",
        f"当前共收录 {len(libs)} 个 Maven 坐标（来源为 Maven Central 搜索翻页与人工种子）：",
        "",
    ]
    lines += [f"- {k}：{v} 个库" for k, v in counts.items()]
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
        "python tools/generate_index.py --crawl --crawl-limit 15000 --workers 24",
        "```",
        "",
        "种子坐标清单见 [tools/seeds/java.json](tools/seeds/java.json)。",
        "",
    ]
    (root / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="tools/seeds/java.json")
    ap.add_argument("--out", default=".")
    ap.add_argument("--limit", type=int, default=0, help="0 = no limit (debug)")
    ap.add_argument("--crawl", action="store_true", help="crawl Maven Central and generate index (seeds are merged in)")
    ap.add_argument("--crawl-limit", type=int, default=4000, help="max artifacts fetched by the crawler")
    ap.add_argument("--workers", type=int, default=24, help="parallel metadata fetch workers")
    ap.add_argument("--refresh-cache", action="store_true", help="ignore cached metadata and fetch everything again")
    args = ap.parse_args()

    root = Path(args.out).resolve()
    seed_path = Path(args.seeds)
    libs = []
    if args.crawl:
        libs = crawl(args)
        if seed_path.exists():
            libs += load_seeds(seed_path)
    else:
        libs = load_seeds(seed_path)
    if args.limit:
        libs = libs[: args.limit]

    cache = load_cache()
    print(f"Processing {len(libs)} libraries from {seed_path}...", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(enrich, lib, cache, not args.refresh_cache) for lib in libs]
        for i, fut in enumerate(as_completed(futures), 1):
            try:
                fut.result()
            except Exception as exc:  # keep going on transient API failures
                print(f"  [{i}/{len(libs)}] enrich error -> {exc}", flush=True)
            if i % 500 == 0 or i == len(futures):
                save_cache(cache)
                print(f"  enriched {i}/{len(libs)}", flush=True)

    save_cache(cache)
    counts = generate(root, libs, root)
    print("Generated per release:", json.dumps(counts, sort_keys=True), flush=True)
    write_java_readme(root, counts, libs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
