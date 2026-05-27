# ot-agent

[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![IEC 62443](https://img.shields.io/badge/standard-IEC%2062443-green.svg)](https://www.iec.ch/homepage)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Air-gap ready](https://img.shields.io/badge/deployment-air--gap%20ready-orange.svg)](#deployment)

**Agentic OT asset classification, risk scoring, and IEC 62443 control recommendation — fully air-gapped.**

Built on top of [ot-asset-classifier](https://github.com/dakhasuresh/ot-asset-classifier), this agent adds:

- **Hybrid classification** — deterministic rules engine for known devices (confidence 1.0), local LLM fallback for ambiguous assets (Ollama / vLLM)
- **Three-tier control generation** — zone-static + device-category + LLM contextual (RAG-grounded in IEC 62443 standard text)
- **Chat interface** — multi-turn conversational agent for ad-hoc queries
- **Batch pipeline** — process full CSV/JSON asset registers with coloured terminal output and structured reports
- **REST API** — FastAPI endpoints for integration into existing security tooling
- **Zero external calls** — everything runs on localhost; designed for air-gapped OT environments

---

## Architecture

```
Asset input  (chat query  OR  CSV/JSON batch)
       │
       ▼
 OTAgentOrchestrator
       │
       ├─► classify_asset
       │       ├── deterministic  →  ot-asset-classifier rules engine  (confidence 1.0)
       │       └── LLM fallback   →  Ollama / vLLM                     (confidence 0.65–0.95)
       │
       ├─► score_risk
       │       └── T × V × I model  (0–125 scale, Critical / High / Medium / Low)
       │
       └─► generate_controls
               ├── Tier 1  zone static     →  IEC 62443-3-2 / 3-3 clause mapping  (always)
               ├── Tier 2  category rules  →  PLC / SIS / HMI / Historian rules    (always)
               └── Tier 3  LLM contextual  →  RAG + Mistral, threat-specific        (Critical / High only)
                               │
                               └── ChromaDB  ←  IEC 62443-2-1 / 2-4 / 3-2 / 3-3 docs
```

Every output carries `classification_path` (`deterministic` | `llm` | `unmatched`) and control `source` (`zone_static` | `category_static` | `llm_contextual`) so every decision is auditable.

---

## Prerequisites

**Python 3.9+** and **Ollama** (for air-gapped LLM inference).

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull required models
ollama pull mistral:7b-instruct   # classification + control generation
ollama pull nomic-embed-text      # RAG embeddings
```

Alternatively, point `LLM_BACKEND=vllm` at a local vLLM server — see [Environment variables](#environment-variables).

---

## Installation

```bash
git clone https://github.com/dakhasuresh/ot-agent.git
cd ot-agent
pip install -e ".[dev]"
```

---

## Quickstart

### 1. Build the RAG knowledge index

Add IEC 62443 source documents (`.txt`, `.md`, or `.pdf`) to `knowledge/docs/`:

```
knowledge/docs/
    62443-2-1.txt
    62443-2-4.txt
    62443-3-2.txt       ← most important for zone/conduit requirements
    62443-3-3.txt       ← most important for security requirements (SR clauses)
```

Then index:

```bash
python -m knowledge.build_index

# Wipe and rebuild from scratch:
python -m knowledge.build_index --reset

# Index a single file:
python -m knowledge.build_index --file knowledge/docs/62443-3-3.txt
```

The agent runs without an index (tiers 1 + 2 always fire), but tier 3 contextual controls are only generated once the index exists.

### 2. Interactive chat (REPL)

```bash
python -m interfaces.chat
```

```
You: Classify a Triconex SIS at a gas processing facility

Agent:
  Safety Instrumented System (SIS)
    Purdue level:   L1
    IEC 62443 zone: Safety
    Category:       SAFETY_SYSTEM
    Classified by:  deterministic rules engine (confidence: 100%)

    Risk score: 100/125 — Critical
    T=5  V=4  I=5

    Active threat patterns:
      • TP-01: Nation-State APT — Critical Infrastructure Targeting
      • TP-08: Safety System Bypass — Zone Boundary Violation
      • TP-04: Supply Chain Compromise — Vendor Software/Firmware

    Priority controls:
      [zone]   IEC 62443-3-2 §6.2: Assign SL3 minimum to all safety zone assets...
      [zone]   IEC 62443-3-3 SR 3.6: Verify deterministic output integrity...
      [device] IEC 62443-3-3 SR 3.6: SIS firmware changes require dual authorisation...
      [AI]     IEC 62443-2-4 §SP.09.01: Time-limit all vendor remote access to SIS...
```

### 3. Batch pipeline

```bash
python -m interfaces.batch --input examples/sample_assets.csv --output report.json
```

See [`examples/sample_assets.csv`](examples/sample_assets.csv) for the input format.

Output options: `--output report.json` or `--output summary.csv`.

```
  [   1/6] [DET] Safety Instrumented System (SIS)          L1     Safety             100 (Critical)
  [   2/6] [DET] Programmable Logic Controller (PLC)       L1     Critical OT         80 (Critical)
  [   3/6] [DET] SCADA Server                              L2     Critical OT         60 (High)
  [   4/6] [DET] Process Historian                         L3     General OT          45 (High)
  [   5/6] [DET] OT Jump Server / Privileged Access Wks    L3.5   IT/OT Boundary      20 (Medium)
  [   6/6] [LLM] Custom RTU Panel                          L1     Critical OT         72 (Critical)

  Total:          6
  Deterministic:  5  (83%)
  LLM path:       1  (17%)
  Unmatched:      0  — review required

  Risk distribution:
    Critical      3  ███
    High          2  ██
    Medium        1  █
    Low           0
```

### 4. REST API

```bash
uvicorn interfaces.chat:app --host 0.0.0.0 --port 8080
```

```bash
# Health check
curl localhost:8080/health

# Create a chat session
curl -X POST localhost:8080/sessions
# → {"session_id": "3fa85f64-..."}

# Chat
curl -X POST localhost:8080/sessions/3fa85f64-.../chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What controls does a Siemens S7-1500 PLC need?"}'

# Single classify (no session)
curl -X POST localhost:8080/classify \
  -H "Content-Type: application/json" \
  -d '{"device_type": "PLC", "manufacturer": "Siemens", "model": "S7-1500"}'

# Conversation history
curl localhost:8080/sessions/3fa85f64-.../history
```

---

## Classification paths

| Path | Trigger | Confidence |
|---|---|---|
| `deterministic` | Matched by ot-asset-classifier rules engine | 1.0 |
| `llm` | No rule matched; LLM confidence ≥ 0.65 | 0.65–0.95 |
| `unmatched` | No rule matched and LLM confidence < 0.65 | 0.0 — flagged for review |

The `unmatched` path is intentional. Assets the agent cannot classify with confidence are flagged in every report for manual review — mixing uncertain and certain results without distinguishing them is how OT security assessments produce unreliable outputs.

---

## Control generation tiers

| Tier | Source | Fires when |
|---|---|---|
| 1 — Zone static | Hardcoded zone → IEC 62443 clause mapping | Always |
| 2 — Category rules | Device category (PLC, SIS, HMI, …) → clause mapping | Always |
| 3 — LLM contextual | ChromaDB RAG retrieval + Mistral generation | `risk_band` is Critical or High, and RAG index exists |

Every `ControlRecommendation` in the output carries:
- `clause` — the exact IEC 62443 clause reference (e.g. `IEC 62443-3-3 SR 1.1`)
- `source` — `zone_static` | `category_static` | `llm_contextual`
- `priority` — 1 (mandatory) | 2 (recommended) | 3 (best practice)
- `addresses_threat` — which threat pattern it mitigates (LLM tier)
- `rationale` — why this applies to this specific device (LLM tier)

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `LLM_BACKEND` | `ollama` | `ollama` or `vllm` |
| `LLM_BASE_URL` | `http://localhost:11434` | Backend base URL |
| `LLM_MODEL` | `mistral:7b-instruct` | Model name |
| `LLM_TIMEOUT` | `120` | Request timeout in seconds |

For vLLM:
```bash
export LLM_BACKEND=vllm
export LLM_BASE_URL=http://localhost:8000
export LLM_MODEL=mistralai/Mistral-7B-Instruct-v0.3
```

---

## Project structure

```
ot-agent/
├── agent/
│   ├── orchestrator.py     # main agent — chat sessions, batch jobs, pipeline
│   └── tools.py            # classify_asset, score_risk, generate_controls
├── knowledge/
│   ├── build_index.py      # one-time indexer: chunk → embed → ChromaDB
│   ├── chroma_store.py     # runtime retrieval wrapper
│   └── docs/               # place IEC 62443 source documents here
├── llm/
│   └── client.py           # Ollama / vLLM unified async client
├── interfaces/
│   ├── chat.py             # REPL + FastAPI app
│   └── batch.py            # CSV/JSON batch pipeline
├── examples/
│   ├── sample_assets.csv   # example batch input
│   └── sample_report.json  # example batch output
├── tests/
│   └── test_pipeline.py
└── schemas.py              # all Pydantic types
```

---

## Running tests

```bash
pytest tests/ -v
```

---

## Deployment

The agent is designed for air-gapped OT environments:

- **No external network calls** — all LLM inference and embedding via local Ollama/vLLM
- **No cloud dependencies** — ChromaDB persists locally to `knowledge/chroma_db/`
- **Graceful degradation** — if the RAG index is empty, tiers 1 + 2 still fire; if Ollama is unreachable, the deterministic path still works

For production deployment, run the FastAPI app behind a reverse proxy (nginx) on a dedicated OT security workstation in the IT/OT boundary zone.

---

## Relationship to ot-asset-classifier

This repo builds on [ot-asset-classifier](https://github.com/dakhasuresh/ot-asset-classifier), which provides the deterministic rules engine, T×V×I risk model, and 14 threat-actor patterns.

`ot-agent` adds the LLM orchestration layer, RAG knowledge base, three-tier control generation, chat interface, and batch pipeline. The two repos are intentionally separate: `ot-asset-classifier` remains a zero-dependency library that any pipeline can consume; `ot-agent` is the opinionated application layer on top.

---

## Roadmap

- [ ] Structured Excel output with gap analysis sheet and conditional formatting
- [ ] Multi-site batch support — per-site zone summaries
- [ ] LLM-generated remediation roadmaps (prioritised by risk band)
- [ ] Vector store support for additional standards (NIST 800-82, NERC CIP)
- [ ] Web UI for the chat interface

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Author

**Suresh Dakha**
Senior Solution Architect — Physical AI, Edge AI & OT Cybersecurity
[linkedin.com/in/suresh-dakha](https://linkedin.com/in/suresh-dakha)

---

## Licence

MIT — see [LICENSE](LICENSE)
