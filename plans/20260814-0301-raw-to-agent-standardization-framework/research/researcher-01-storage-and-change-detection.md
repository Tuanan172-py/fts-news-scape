# Producer-Side Raw HTML Storage & Change Detection Framework
## Research Report: Storage Architecture, Provenance, and Incremental Processing

---

## 1. Layered Data Architecture (Bronze/Silver/Gold)

**Pattern**: Medallion architecture organizes raw web-content corpus via immutable layers:

- **Bronze (Raw)**: Byte-exact HTML + `.meta.json` sidecar, content-addressed at `data/raw_html/<domain>/<yyyymmdd>/<hash>.html`. Immutable, never backfilled/corrected. Partitioned by source domain + date for parallel scrapability and cost-efficient time-range queries.
- **Silver (Cleaned)**: Deduplicated, templated HTML (removed boilerplate), structured text extraction, schema-validated. Backward-compatible JSONL or Parquet with versioned schema.
- **Gold (Curated)**: Aggregated, enriched datasets (topic classification, entity tagging, cross-reference links) ready for downstream agents. Serves SLA-bound analytics contracts.

**Partition Convention**: `<layer>/<domain>/<year>/<month>/<day>/` enables efficient time-windowed re-processing (e.g., "re-extract Silver for washingtonpost.com Jan 2026"). Each file tagged with `schema_version` in metadata.

**Immutability Enforcement**: Bronze layer write-once, read-many (WORM); failed scrapes do NOT overwrite or delete. Enforce via filesystem ACLs or object storage versioning (S3 MFA delete, Azure blob versions).

**Refs**: [Databricks Medallion](https://docs.databricks.com/aws/en/lakehouse/medallion), [Microsoft Fabric](https://learn.microsoft.com/en-us/fabric/onelake/onelake-medallion-lakehouse-architecture)

---

## 2. Content-Addressed + Versioned Storage & Provenance

**Content Addressing**: Derive file hash from raw HTML: `hash = SHA256(raw_bytes)`. Name file `<hash>.html`. This deduplicates identical articles scraped from multiple sources and ties each article to its exact byte representation.

**Manifest Format** (per-domain scrape-run):
```jsonl
{
  "capture_id": "washingtonpost.com-20260814",
  "timestamp_utc": "2026-08-14T03:01:00Z",
  "articles": [
    {
      "url": "https://...",
      "content_hash": "abc123def456...",
      "file_path": "data/raw_html/washingtonpost.com/20260814/abc123def456.html",
      "byte_size": 45230,
      "http_status": 200,
      "headers": {"content-type": "text/html; charset=utf-8"},
      "scraped_by": "news-scraper-v2.1.4",
      "page_load_time_ms": 1245
    }
  ]
}
```

**Dataset Snapshot** (catalog-of-catalogs): Single `manifest-of-manifests.jsonl` listing all domain manifests by date:
```jsonl
{"date": "20260814", "manifest_url": "s3://bucket/data/manifests/20260814/manifest.jsonl", "domains_count": 47}
```

**Provenance Metadata**: Each article tagged with WHEN (timestamp), WHERE (URL + HTTP headers), HOW (scraper version, load time, JavaScript rendering flag). Enables replay with same tool/config.

**WARC vs. Plain HTML+JSON**: WARC (ISO 28500:2017) is industry-standard for web archiving (includes HTTP headers, response codes, timestamps). Plain HTML+JSON+manifest is lighter, queryable (JSONL for streaming, Parquet for analytics), and already matches your byte-exact design. **Recommendation**: Stay with plain HTML+JSON for producer; emit WARC archive for long-term preservation/access audit if needed later.

**Refs**: [WARC Format](https://archive-it.org/blog/the-stack-warc-file/), [Scrapfly WARC Reference](https://scrapfly.io/docs/crawler-api/warc-format), [DataOps Versioning](https://www.thedataops.org/versioning/)

---

## 3. HTML Change Detection for Re-Scrape

**Fingerprinting Algorithms**:

| Technique | Use Case | Cost | Notes |
|-----------|----------|------|-------|
| **SHA256 Full** | Exact match detection | O(n) | Detects any byte difference; too sensitive for template changes |
| **SimHash (64-bit)** | Near-duplicate + drift | O(1) lookup | Charikar LSH; similar docs differ by few bits; robust to whitespace/tag reordering |
| **MinHash Sketches** | Large-scale dedup | O(k) space | K-mer shingles; fast set similarity; overkill for small corpus |
| **DOM Tree Hash** | Template detection | O(d) depth | Hash DOM structure after filtering dynamic nodes (ads, timestamps, comments) |

**Recommended Stack**:
1. **Canonical Hash** (SHA256 of raw bytes) → store in manifest with every scrape
2. **SimHash64 Fingerprint** → compute and compare across runs to detect template/structural changes
3. **CSS Selector Snapshot** → log main content selectors (e.g., `article.main-content`, `div.story-body`) to detect selector drift (CMS migration breaking old extraction)

**Change Detection Log**:
```jsonl
{
  "url": "https://example.com/article/123",
  "scrape_date": "20260814",
  "canonical_hash": "abc123...",
  "simhash64": "0x1234567890abcdef",
  "comparison_to_previous": {
    "previous_hash": "abc122...",
    "hamming_distance": 2,
    "changed": true,
    "change_type": "content_modified"  // vs. "template_only" vs. "selector_broken"
  },
  "selectors_used": ["article.story", "div.body-text"],
  "selector_drift": false,
  "recommendation": "re_extract"  // vs. "skip" vs. "manual_review"
}
```

**Tools/Libraries**: Python `simhash-py`, Google's [near-duplicate detection paper](https://research.google.com/pubs/archive/33026.pdf), DOM fingerprinting via BeautifulSoup4 tag-path hashing.

**Refs**: [SimHash Guide](https://spotintelligence.com/2023/01/02/simhash/), [Content Fingerprinting](https://inferensys.com/glossary/programmatic-content-infrastructure/automated-metadata-tagging/content-fingerprinting/), [Google Near-Dup Detection](https://research.google.com/pubs/archive/33026.pdf)

---

## 4. Packaging "Clean Base" for Downstream Consumers

**Per-Article Work Package** (self-contained, serializable):
```jsonl
{
  "work_id": "article-abc123",
  "raw_html_path": "s3://bucket/data/raw_html/example.com/20260814/abc123.html",
  "metadata": {
    "url": "https://example.com/article",
    "domain": "example.com",
    "scraped_at": "2026-08-14T03:01:00Z",
    "content_hash": "abc123",
    "schema_version": "article-v2.1"
  },
  "manifest_path": "s3://bucket/data/manifests/20260814/example.com-manifest.jsonl"
}
```

**Data Contract** (OpenMetadata-style):
```yaml
name: news_article_raw_html
version: "2.1"
semantics:
  pii_fields: ["author_name", "source_url"]
  entity_types: ["article", "news", "web_content"]
schema:
  type: object
  properties:
    raw_html:
      type: string
      description: "Byte-exact HTML capture"
    domain:
      type: string
    scraped_at:
      type: string
      format: "iso8601"
compatibility: BACKWARD_TRANSITIVE  # New consumers can read old schema versions
```

**Catalog/Index** (manifest-of-manifests, queryable):
- Index all scrape runs by date + domain in a single Parquet table: `catalog.parquet`
  - Schema: `(date, domain, manifest_url, article_count, schema_version)`
  - Allows agents to enumerate: `SELECT * FROM catalog WHERE date >= '20260810'`

**Schema Registry**: Use Apache Avro or JSON Schema Draft 2020-12. Register version 2.1 before deploying scrapers using it. Enforce `can_read_old_versions = true` for backward compat.

**Backward Compatibility**: If adding optional field (e.g., `js_rendered_content`), default to `null` for old records. Consumers see consistent schema. If removing field, deprecate 2+ versions first, log warnings.

**Refs**: [Data Contracts Explained](https://atlan.com/data-contracts/), [JSON Schema Versioning](https://www.zerodatatools.com/blog/json-schema-versioning-guide/), [OpenMetadata Standards](https://openmetadatastandards.org/data-contracts/data-contract/), [Parquet Schema Evolution](https://medium.com/data-engineering-with-dremio/all-about-parquet-part-04-schema-evolution-in-parquet-c2c2b1aa6141)

---

## 5. Idempotency & Incremental Processing

**Watermark Strategy**:
- **Watermark Column**: Track `last_scraped_date` per (domain, URL) in a lightweight state table (SQLite/DuckDB or S3 CSV).
- **Stateless Scraper**: At start of run, query state table: "which domains have URLs last scraped before 2026-08-14?" Only scrape those.
- **Commit Watermark** AFTER successful storage to Bronze + manifest write. If scraper crashes mid-run, next invocation retries from last committed watermark (no gap).

**Exactly-Once Handoff** (Producer → Consumer):
1. **Producer (Scraper)** writes Bronze + manifest atomically (either both succeed or both fail). Include `capture_id` (unique per run) in manifest.
2. **Consumer (Agent)** polls manifest catalog, reads `last_consumed_capture_id` from state.
3. Only processes new captures (capture_id > last_consumed). If agent crashes mid-processing, restart from same capture (idempotent).
4. **Idempotency Key**: Manifest `capture_id` + article `content_hash` uniquely identifies work. Replaying idempotent (no duplicate rows if consumer re-reads same manifest).

**Processed Markers**:
```json
{
  "capture_id": "example.com-20260814-001",
  "status": "processing",
  "processed_at": null,
  "error": null
}
```
→ After successful extraction: `"status": "processed"`, `"processed_at": "2026-08-14T03:15:00Z"`
→ On error: `"status": "failed"`, `"error": "selector_broken_author_byline"`

**Incremental Window**: Default to re-scraping only URLs changed in past 7 days (or template-drift detection). For high-churn sites, shorten window. Store as config per domain.

**Refs**: [Exactly-Once Semantics in Kafka](https://www.conduktor.io/glossary/exactly-once-semantics-in-kafka), [Idempotent Processing with Kafka](https://nejckorasa.github.io/posts/idempotent-kafka-procesing/), [Watermarks in Stream Processing](http://www.vldb.org/pvldb/vol14/p3135-begoli.pdf), [Google Dataflow Exactly-Once](https://docs.cloud.google.com/dataflow/docs/concepts/exactly-once)

---

## Recommendation

Adopt a **three-layer medallion architecture** with immutable Bronze (SHA256-addressed raw HTML + manifest), incremental Silver (deduplicated JSONL), and Gold (schema-versioned Parquet). Use **SimHash64 + DOM fingerprinting** for change detection to decide re-scrape vs. skip. Package work for consumers via **per-article JSON manifest + catalog index**. Enforce **data contracts** (JSON Schema + BACKWARD_TRANSITIVE compatibility) in CI/CD gates. Implement **watermarks + idempotency keys** (capture_id + content_hash) for exactly-once producer→consumer semantics.

---

## Unresolved Questions

1. **Handling soft-404s & republished URLs**: How to distinguish "page removed" vs. "template broken" in change logs? Should failed scrapes create a "null" entry in manifest or be omitted?
2. **Manifest file size at scale**: At 1M+ articles/day, should single domain manifest be sharded (by hour) or remain daily? Queryability vs. atomicity trade-off.
3. **Content-hash collisions on malicious input**: Should manifest store both SHA256 + size as composite key to mitigate SHA256 collision attacks on untrusted HTML?
4. **Consumer polling frequency**: What watermark commit cadence balances exactly-once guarantee vs. latency? Batch-per-domain-run or per-X-articles?
