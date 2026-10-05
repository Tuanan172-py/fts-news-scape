# Provider-Agnostic Agent Framework for Structured News Processing

**Research Date:** 2026-08-14  
**Sources:** 5 parallel web searches + academic literature  
**Scope:** Consumer-side agent I/O standardization, provider-neutral execution contracts, quality gates

---

## 1. Provider-Agnostic I/O Contract

### Status Quo (2026)

**Pragmatic Convergence, Not Full Standardization:**  
OpenAI function calling, Anthropic tool use, Gemini responseSchema all expose JSON Schema + tool names + descriptions, but subtle differences force provider-specific code paths. No single universal format yet exists.

**Neutral Spec: Model Context Protocol (MCP)**  
- Introduced by Anthropic (Nov 2024), adopted as industry standard by 2026  
- JSON Schema–based, provider-agnostic  
- Supported by LangChain, CrewAI, OpenAI SDK, Claude Desktop, Microsoft Agent Framework  
- **Key:** MCP defines tool interface (name, description, schema) independently of provider  

**Multi-Provider Solutions (2026):**  
- **Microsoft Agent Framework:** Native support for OpenAI, Anthropic, Bedrock, Gemini, Ollama  
- **Smolagents:** Model-agnostic via LiteLLM wrapper (OpenAI, Anthropic, Gemini, local Transformers)  

### Recommendation for Raw → Agent Handoff

**Input Contract (Canonical):**
```json
{
  "article_id": "string (UUID or unique id)",
  "source_url": "string (original publication URL)",
  "captured_at": "ISO8601 timestamp",
  "raw_html_path": "string (local filesystem path to raw HTML)",
  "cleaned_text": "string (human-readable text extracted)",
  "metadata": {
    "source_domain": "string",
    "publication_date": "ISO8601 or null",
    "language": "string (BCP47 code, e.g., 'vi', 'en')",
    "byline": "string or null",
    "content_hash": "string (SHA256 of raw_html)"
  }
}
```

**Output Contract (MCP Tool Response):**  
Return as JSON-serialized structured object (identical across providers):
```json
{
  "article_id": "string",
  "output_schema_version": "1.0",
  "fields": { /* see canonical schema below */ },
  "processing_metadata": {
    "agent_provider": "string (openai|anthropic|gemini|local)",
    "model_used": "string",
    "timestamp": "ISO8601",
    "execution_time_ms": "integer"
  }
}
```

**Portability Strategy:**  
1. Encode input/output as JSON Schema documents (vendor-neutral)  
2. Wrap provider-specific API calls (OpenAI, Anthropic, Gemini) with adapter layer  
3. Use MCP for tool definitions; delegate provider auth/retry logic to adapters  
4. Validate output schema before returning (prevents silent provider drift)

---

## 2. Output Field Taxonomy for News/Financial Analysis

### Canonical Schema (Recommended)

Based on FinBERT, financial NLP pipelines, and entity-level sentiment research:

```json
{
  "tóm tắt": {
    "abstractive_summary": "string (2-3 sentences, AI-generated)",
    "summary_type": "enum (abstractive|extractive)",
    "key_quotes": ["string"] // 1-3 direct quotes from source
  },
  "hàm ý": {
    "implication": "string (2-3 sentence explanation of 'so what')",
    "affected_parties": ["string"], // e.g., ["Apple Inc.", "Taiwan", "US tech sector"]
    "potential_impact_area": "enum (market|regulatory|sentiment|supply_chain|geopolitical)"
  },
  "mức độ quan trọng": {
    "materiality_score": "float [0.0..1.0]", // importance for markets/investors
    "time_sensitivity": "enum (urgent|today|this_week|this_month|archive)",
    "confidence": "float [0.0..1.0]" // model confidence in this assessment
  },
  "entities": {
    "companies": [{"ticker": "string", "name": "string", "sentiment": "float [-1..1]"}],
    "people": [{"name": "string", "role": "string|null"}],
    "locations": ["string"],
    "financial_instruments": [{"type": "string", "symbol": "string"}]
  },
  "sentiment_analysis": {
    "overall_sentiment": "float [-1.0..1.0]", // -1: very negative, 0: neutral, +1: very positive
    "sentence_sentiments": [{"text": "string", "score": "float"}], // optional: sample 3-5 key sentences
    "sentiment_model_used": "string (e.g., 'FinBERT', 'bloomberg-gpt')"
  },
  "event_classification": {
    "event_type": "enum (earnings|acquisition|regulatory|lawsuit|partnership|financial_move|sentiment|other)",
    "sub_category": "string|null"
  },
  "citations": [
    {
      "claim": "string (the statement being cited)",
      "source_span": "string (exact text from raw_html)",
      "source_char_offset": "integer (0-based position in cleaned_text)"
    }
  ],
  "processing_notes": {
    "language_detected": "string (BCP47)",
    "extraction_quality": "enum (high|medium|low)",
    "warnings": ["string"] // e.g., ["Machine-translated from Vietnamese", "Source is paywalled"]
  }
}
```

### Field Justification

| Field | Standard | Why |
|-------|----------|-----|
| **tóm tắt** | Abstractive + extractive | News requires both AI summary + direct quotes for verification |
| **hàm ý** | LLM-inferred implication | Critical for investment decision-making; not explicitly in source |
| **mức độ quan trọng** | Materiality score + time-sensitivity | Financial materiality = will this move markets; time matters for actioners |
| **entities** | Entity-level sentiment | FinEntity (2023 EMNLP) shows entity-level beats document-level for finance |
| **citations** | Exact source mapping | Groundedness critical in regulated finance; auditable chain |
| **confidence** | Model confidence score | Enables downstream filtering; supports human-in-loop workflows |

---

## 3. Orchestration & Workflow Patterns

### LangGraph as Reference (2026 Production Standard)

**State Machine + Checkpointing:**  
Model workflow as DAG with nodes (tool calls, LLM invocations) and edges (transitions). Supports:
- **Persistent checkpoints** (PostgreSQL, Redis) → workflow survives restarts/crashes  
- **Streaming state** → client sees reasoning in real-time  
- **Interruption + resume** → human approval gates

**2026 Winning Pattern:** Deterministic backbone (flow) + agent invoked *intentionally* at specific steps. Agent completes → control returns to flow (not autonomous loops).

### Multi-Article Pipeline (Recommended)

```
[Raw HTML Store]
    ↓
[Router/Dispatcher] ← Load batch of N articles
    ↓
[Parallel Extractor Agents] ← Fan-out to OpenAI/Anthropic/Gemini
    ↓
[Aggregator] ← Collect results, merge duplicates
    ↓
[Critic/Verifier Agent] ← LLM-as-judge: check schema compliance, groundedness
    ↓
[Output Writer] → Structured DB/vector store
```

### Subagent Decomposition Roles

| Role | Function | When |
|------|----------|------|
| **Router** | Classify article type; route to domain-specific extractor | Always first |
| **Extractor** | Call LLM with input contract; fill canonical schema | Per-article |
| **Analyst** | Enrich implication, materiality (loop: recursive refinement) | 1-2 iterations if confidence < 0.7 |
| **Verifier** | Schema validation, citation verification, hallucination check | Before output write |
| **Aggregator** | Dedupe cross-source duplicates, merge related articles | Post-parallel execution |

### Loop Conditions

- **Map-reduce on batch:** Split 100 articles → 10 workers → merge outputs  
- **Iterative refinement:** If materiality confidence < threshold, re-analyze with additional context  
- **Adversarial verify:** Query agent: "Critique the implication; is it overreaching?" Then reconcile

---

## 4. Execution Governance

### Task Lifecycle (MCP 2026 Spec)

**Stateless Model:** Server returns task handle; client drives workflow:
- `tasks/create` → agent accepts article  
- `tasks/get` → poll status  
- `tasks/update` → heartbeat/progress  
- `tasks/cancel` → abort if timeout  

**Retry Semantics:** Not enforced by MCP; fallback to JSON-RPC + message queue. **Must implement at adapter layer.**

### Idempotency & Durable State

**Challenge:** Multiple retries can produce duplicate outputs.  
**Solution (2026 practice):**
1. Content hash each input (SHA256 of raw_html) → acts as deterministic ID  
2. Checkpoint output with hash + timestamp  
3. If same hash seen again: return cached result (TTL-based expiry)  
4. Compensation logic for partial failure (e.g., if extractor succeeds but verifier fails: roll back checkpoint)

### Definition of Done Signal

**Article marked COMPLETE when:**
1. Schema validation passes (all required fields populated)  
2. Confidence score ≥ threshold (configurable, e.g., 0.65)  
3. At least 2 citations mapped to source text  
4. Processing_notes.extraction_quality ∈ [high, medium]  
5. Timestamp + agent_provider logged (auditable)

**Intermediate states:** STARTED, EXTRACTION_PENDING, VERIFICATION_PENDING, FAILED_RECOVERABLE, FAILED_PERMANENT

### Human-in-Loop Gates

- **Pre-processing:** Human reviews routing rules (is this a market-moving event?)  
- **Post-extraction:** High-confidence (>0.8) auto-publishes; 0.5–0.8 flags for review  
- **Post-verification:** Critic raises concerns → human overrides or re-runs

---

## 5. Evaluation & Quality Gates

### Schema Validation

Validate output against canonical JSON Schema before writing:
```python
from jsonschema import validate, ValidationError
validate(instance=agent_output, schema=canonical_schema)
# Fails loudly if required field missing or type mismatch
```

### LLM-as-Judge Pattern (2026 Standard)

**Three Checks:**
1. **Faithfulness:** Does implication follow from source text? Judge: "Rate 1–5: Is the implication grounded in the article?"  
2. **Groundedness:** Citation quality. Judge: "Can you verify each claim with a quote?"  
3. **Completeness:** Coverage. Judge: "Are all key entities and impacts identified?"

**Rubric Decomposition:** Recursive rubrics (2026 research) outperform flat scoring.

### Concrete Metrics

| Metric | Formula | Target |
|--------|---------|--------|
| **Schema Compliance** | (articles passing validation / total) × 100 | ≥ 98% |
| **Citation Coverage** | (avg citations per article) | ≥ 2 per article |
| **Confidence Distribution** | % articles with confidence > 0.7 | ≥ 80% |
| **Hallucination Rate** | (judge marks unfounded claims / total articles) × 100 | ≤ 2% |
| **Latency (p95)** | Time from input → output | ≤ 15s per article |

### Regulatory Compliance (2026 Context)

EU AI Act + NIST AI RMF + ISO/IEC 42001 now require:
- Version control: datasets, prompts, judge models (treat as code)  
- Audit trail: who processed, which model, confidence scores  
- Reproducibility: same input + model + seed = same output

---

## Recommended Canonical Schema (Summary)

**Core Fields (Always Required):**
```json
{
  "article_id": "string",
  "tóm tắt.abstractive_summary": "string",
  "tóm_tắt.key_quotes": ["string"],
  "hàm_ý.implication": "string",
  "hàm_ý.affected_parties": ["string"],
  "mức_độ_quan_trọng.materiality_score": "float [0..1]",
  "mức_độ_quan_trọng.confidence": "float [0..1]",
  "entities.companies": ["object (ticker, name, sentiment)"],
  "sentiment_analysis.overall_sentiment": "float [-1..1]",
  "event_classification.event_type": "enum",
  "citations": ["object (claim, source_span, offset)"],
  "processing_metadata.agent_provider": "string",
  "processing_metadata.timestamp": "ISO8601"
}
```

**Extensible Fields (Optional but Recommended):**
- `entities.people`, `.locations`, `.financial_instruments`  
- `sentiment_analysis.sentence_sentiments[]`  
- `processing_notes.warnings[]`

---

## Unresolved Questions

1. **Multi-language Support:** How to handle Vietnamese source → multilingual agents (translate or analyze in-language)? Trade-off: translation loss vs. domain adaptation.
2. **Hallucination Threshold:** What confidence cutoff triggers human review? Finance is high-stakes; is 0.7 enough?
3. **Real-time vs. Batch:** Should orchestration support both streaming ingestion (1 article at a time) and batch (100+)?
4. **Provider Failover:** If OpenAI is down, auto-fallback to Anthropic? Requires output format lock + retry logic.
5. **Cost Optimization:** Multi-provider routing (cheap model for low-materiality, expensive for high-stakes)—where to implement?
6. **Citation Verification at Scale:** LLM-as-judge for citations scales poorly (cost/latency). Heuristic alternatives?

---

## Sources

- [AI Agents 2026 — Guide from LLM to Multi-Agent Systems | EITT](https://eitt.academy/knowledge-base/ai-agents-2026-guide-from-llm-to-multi-agent-systems/)
- [Unified Tool Integration for LLMs: A Protocol-Agnostic Approach to Function Calling](https://arxiv.org/html/2508.02979v1)
- [The best AI agent frameworks in 2026 | LangChain](https://www.langchain.com/resources/ai-agent-frameworks)
- [AI Agent Frameworks (2026 Update): 8 SDKs Compared + the Claude Agent SDK Primitive Reference](https://www.morphllm.com/ai-agent-framework)
- [LLM API Parameter Compatibility Reference - Anthropic, OpenAI, Google Gemini, and Amazon Bedrock](https://hidekazu-konishi.com/entry/llm_api_parameter_compatibility_reference.html)
- [NLP Market Sentiment 2026: AI-Driven Sentiment Scoring for Investors](https://pooya.blog/blog/nlp-market-sentiment-analysis-words-move-markets-2026/)
- [Financial News Sentiment Analysis Explained | NowNews](https://nownews.dev/blog/financial-news-sentiment-analysis-explained)
- [FinEntity: Entity-level Sentiment Classification for Financial](https://aclanthology.org/2023.emnlp-main.956.pdf)
- [LLM Workflows: Patterns, Tools & Production Architecture (2026) | Morph](https://www.morphllm.com/llm-workflows)
- [Architecting Resilient LLM Agents: A Guide to Secure Plan-then-Execute Implementations](https://arxiv.org/pdf/2509.08646)
- [LangGraph Agent Patterns 2026: Building Stateful Multi-Step AI Workflows](https://callsphere.ai/blog/langgraph-agent-patterns-2026-stateful-multi-step-ai-workflows)
- [LangGraph in 2026: building production AI agents as state machines, not chatbots](https://www.reactify-solutions.com/articles/langgraph-production-agents-2026)
- [The 2026 MCP Roadmap | Model Context Protocol Blog](https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/)
- [Agent Interoperability Protocols 2026: MCP, A2A, ACP and the Path to Convergence](https://zylos.ai/research/2026-03-26-agent-interoperability-protocols-mcp-a2a-acp-convergence/)
- [Governance Gaps in Agent Interoperability Protocols: What MCP, A2A, and ACP Cannot Express](https://arxiv.org/pdf/2606.31498)
- [The 2026-07-28 MCP Specification Release Candidate](https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/)
- [From Question Answering to Task Completion: A Survey on Agent System and Harness Design](https://arxiv.org/pdf/2606.20683)
- [LLM as a Judge: A 2026 Guide to Automated Model Assessment](https://labelyourdata.com/articles/llm-as-a-judge)
- [Benchmarking LLM-as-a-Judge for Long-Form Output Evaluation](https://arxiv.org/pdf/2606.01629)
- [LLM-as-a-Judge in 2026: Top evaluation techniques and best practices | DeepEval](https://deepeval.com/blog/llm-as-a-judge)
- [the complete guide for LLM evaluations in 2026 | Galtea Blog](https://galtea.ai/blog/llm-evaluation-complete-guide)
