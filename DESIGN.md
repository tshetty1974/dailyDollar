# AI-Native Investment Research System
## Design Document

Built on the Microsoft Agent Framework (Python).

---

## 1. Overview

### 1.1 Problem

Given one or more candidate stocks and an investor's objective - amount, risk
appetite, time horizon - produce a grounded recommendation with a suggested
portfolio allocation. The system must behave like a small team of specialist
analysts: research each candidate from different angles, debate the findings,
pressure-test the conclusion, and explain itself. It must be conversational,
remember the user across sessions, and be traceable end to end.

### 1.2 What the system does

Eight agents, one orchestration, three persistence layers and two front ends.
A run researches each candidate through a manager-led workflow, produces a draft
recommendation, subjects it to a bull-versus-skeptic debate, redrafts in light of
that debate, has a critic score the result, and writes the accepted answer to
long-term memory. Every claim in the output names its source; every step emits
an OpenTelemetry span.

### 1.3 Scope boundaries

- **Fundamentals are only grounded for companies whose filings have been ingested.**
  Other listed companies are analysed on price, news and macro; the system says
  so explicitly rather than silently producing a weaker answer.
- **This is a research tool, not an advisory product.** It produces analysis with
  stated assumptions, not personalised financial advice, and does not execute
  trades.

---

## 2. Requirements traceability

| # | Requirement | Implemented in | Evidence |
|---|---|---|---|
| 3.1 | Multi-agent research team | `src/agents/` - 8 agents | Each has a bounded remit and explicit prohibitions |
| 3.2 | Central orchestration | `investment_orchestrator.py` - `MagenticBuilder` | Manager plans, delegates, decides sufficiency |
| 3.3 | Structured debate | `run_debate()` - 3 turns | Impact measured by diffing pre/post-debate drafts |
| 3.4 | Reflection & evaluation | `agents/evaluator.py`, `evaluate()` | Scores the brief's three criteria; bounded revision |
| 3.5 | Grounding via RAG | `src/rag/`, `tools/sec_tools.py` | `source` is a required field on every evidence item |
| 3.6 | Short- & long-term memory | `src/memory/` | `AgentSession` + `ContextProvider`; survives restart |
| 3.7 | Checkpointing & resumption | `memory/checkpoint.py` | Completed candidates skipped on resume |
| 3.8 | MCP & A2A | `src/mcp/`, `src/a2a_server.py` | Market data over MCP; Risk Analyst served over A2A |
| 3.9 | Observability | `src/observability.py` | Spans → live timeline, log file, OTLP dashboard |

---

## 3. High-Level Design

### 3.1 System context

| Actor / system | Role |
|---|---|
| User | States an objective, asks follow-up questions |
| Gemini API | The model behind every agent |
| SEC EDGAR | Source of 10-K filings (ingested offline) |
| yfinance | Market data, served through an MCP server |
| Marketaux | News and sentiment |
| OTLP collector | Optional trace dashboard (Jaeger, Aspire, Azure Monitor) |
| A2A clients | External runtimes calling the Risk Analyst |

### 3.2 Architecture

```mermaid
flowchart TB
    User([User])

    subgraph Front["Front ends"]
        CLI["main.py<br/>terminal"]
        UI["app.py<br/>Streamlit chat"]
    end

    Engine["conversation.py<br/><b>Conversation engine</b>"]
    Assistant["Investment Assistant<br/>AgentSession + memory"]

    subgraph Research["Per candidate: Magentic orchestration"]
        Manager["Research Manager"]
        Fund["Fundamentals"]
        Tech["Technical"]
        News["News and Sentiment"]
        Macro["Macro and Thesis"]
        Risk["Risk"]
    end

    subgraph Debate["Debate: 3 turns"]
        Bull["Bull Analyst"]
        Skeptic["Risk Analyst as skeptic"]
    end

    Draft1["Draft 1<br/>pre-debate"]
    Synth["Synthesis and Allocation<br/>only agent that sizes positions"]
    Eval["Evaluator"]

    subgraph Data["Grounding"]
        Chroma[("Chroma<br/>SEC 10-K chunks")]
        MCPSrv["MCP market server"]
        NewsAPI["News API"]
    end

    subgraph Persist["Persistence"]
        Mem[("memory<br/>profile, holdings, history")]
        Ckpt[("checkpoints<br/>partial run state")]
    end

    A2A["A2A server :9999<br/>agent card + JSON-RPC"]
    Ext([External runtime])

    Otel["OpenTelemetry"]

    User <--> Front
    Front --> Engine
    Engine --> Assistant
    Assistant -.->|reads| Mem
    Engine -->|InvestmentRequest| Manager

    Manager --> Fund
    Manager --> Tech
    Manager --> News
    Manager --> Macro
    Manager --> Risk

    Chroma -.->|evidence| Fund
    MCPSrv -.->|tools| Tech
    NewsAPI -.->|tool| News

    Research --> Draft1
    Draft1 --> Bull
    Bull <--> Skeptic
    Debate --> Synth
    Draft1 -.->|diffed against| Synth
    Synth --> Eval
    Eval -->|revise once: re-synthesise,<br/>no new research| Synth
    Eval -->|accept| Mem

    Risk -.->|also served over A2A| A2A
    Ext -.->|calls without importing| A2A

    Research -.-> Ckpt
    Synth -.-> Otel
    Research -.-> Otel
```

### 3.3 Component responsibilities

| Component | Owns | Does not |
|---|---|---|
| Conversation engine | Turn handling, intent, parameter extraction | Analyse stocks |
| Magentic manager | Who speaks, in what order, when to stop | Recommend or allocate |
| Five specialists | Findings in one lane each | Allocate, or stray into another lane |
| Bull / Skeptic | Arguing the same evidence | Allocate |
| Synthesis | Verdict, conviction, **allocation**, citations | Gather evidence |
| Evaluator | Scoring and rejection | Rewrite the draft |
| Memory | What persists across sessions | Anything within a run |
| Checkpoint | What survives a crash within a run | Anything across runs |

### 3.4 End-to-end flow

1. **Conversation** - one model call reads the user's message, decides chat vs
   analyse, and extracts parameters.
2. **Research** - per candidate, a Magentic workflow runs five specialists across
   four phases. Findings are checkpointed per candidate.
3. **Draft 1** - synthesis produces a recommendation *without* the debate.
4. **Debate** - bull opens, skeptic attacks, bull responds.
5. **Draft 2** - synthesis runs again with the debate and its earlier draft.
6. **Debate impact** - the drafts are diffed; differences are attributable to the
   debate alone.
7. **Evaluation** - the critic scores and may return it once for revision.
8. **Memory** - the accepted recommendation is persisted; the checkpoint is
   cleared.

### 3.5 Technology choices

| Concern | Choice | Why |
|---|---|---|
| Framework | Microsoft Agent Framework | Mandated |
| Orchestration | Magentic | Manager-led, named in the brief |
| Model | `gemini-3.5-flash-lite` | Cheap and fast enough for ~40 calls per run |
| Vector store | Chroma | Local, no service to run |
| Embeddings | `all-MiniLM-L6-v2` | Small, local, no API cost |
| Contracts | Pydantic | Validation, and the schema encodes the rubric |
| Tracing | OpenTelemetry | Named in the brief; vendor-neutral |
| UI | Streamlit | Minimal code over the same engine |

---

## 4. Low-Level Design

### 4.1 Agent roster

| Agent | Input | Tools | Output |
|---|---|---|---|
| Research Manager | Task + objective | - | Delegation decisions, Phase 4 consolidation |
| Fundamentals | SEC evidence injected into the task | - | Financial health, valuation, risks |
| Technical | Ticker | MCP: price, history, indicators | Trend, momentum, volatility |
| News & Sentiment | Ticker | `search_news` | Events, catalysts, sentiment |
| Macro & Thesis | Phase 1 findings | - | Industry, secular trends, thesis |
| Risk | All prior findings | - | Vulnerabilities, downside scenarios |
| Bull | Same findings as skeptic | - | The strongest honest case for |
| Synthesis & Allocation | All findings + debate + objective | - | `PortfolioRecommendation` |
| Evaluator | The draft + objective | - | `Evaluation` |

Every specialist prompt forbids allocation, so exactly one agent sizes positions.

### 4.2 Data contracts

**`InvestmentRequest`** - the input boundary, and the shape memory persists.

| Field | Type | Notes |
|---|---|---|
| `user_id` | str | Keyed per user; multi-user is storage, not redesign |
| `tickers` | list[str] | Uppercased, de-duplicated, min 1 |
| `amount` | float | > 0 |
| `risk_appetite` | enum | conservative / moderate / aggressive |
| `horizon` | enum | short / medium / long |
| `constraints` | list[str] | Free text, e.g. "max 40% in one position" |

`objective_brief()` renders this as prompt text in one place, so every agent reads
the same definition of the user's constraints.

**`PortfolioRecommendation`** - the output boundary.

| Field | Constraint | Requirement it enforces |
|---|---|---|
| `stocks[].evidence[].source` | required | 3.5 traceability |
| `stocks[].debate_resolution` | required | 3.3 "not decorative" |
| `stocks[].assumptions` | min 1 | Explainability NFR |
| `stocks[].key_risks` | min 1 | Explainability NFR |
| `stocks[].conviction` | 1–5 | Confidence, distinct from verdict |
| `stocks[].allocation_percent` | 0–100 | The actual recommendation |
| `cash_percent` | auto-filled | Remainder treated as cash rather than failing |

**`Evaluation`** - three 1–5 scores (evidence quality, risks addressed, fit to
constraints), a verdict enum, and an actionable critique.

### 4.3 Run sequence

```mermaid
sequenceDiagram
    participant U as User
    participant C as Conversation
    participant M as Magentic manager
    participant S as Specialists
    participant B as Bull
    participant K as Skeptic
    participant Y as Synthesis
    participant E as Evaluator
    participant D as Memory

    U->>C: objective in natural language
    C->>C: extract InvestmentRequest
    loop per candidate
        C->>M: task + SEC evidence
        M->>S: delegate across 4 phases
        S-->>M: findings
        C->>C: checkpoint findings
    end
    C->>Y: findings only
    Y-->>C: Draft 1
    loop per candidate
        C->>B: make the case
        B-->>K: bull case
        K-->>B: rebuttal
        B-->>C: response
    end
    C->>Y: findings + debate + Draft 1
    Y-->>C: Draft 2
    C->>C: diff drafts = debate impact
    C->>E: score Draft 2
    alt revise
        E-->>Y: critique
        Y-->>C: revised draft
    end
    C->>D: persist recommendation
```

### 4.4 Orchestration

`MagenticBuilder` with five participants, `max_round_count=25`,
`max_stall_count=3`. A **fresh workflow per candidate**, so one stock's
conversation cannot leak into another's.

The manager's closing summary is captured, but synthesis receives the
specialists' **raw text**: the manager compresses "$39,520M in marketable
securities (10-K 2026-02-25, Item 15)" into "strong liquidity", and you cannot
cite what was summarised away.

Findings are harvested from workflow events defensively - payloads arrive as a
lone response, a list, or an `AgentExecutorResponse` wrapper depending on the
event.

### 4.5 Debate

Three turns, run as explicit calls rather than inside Magentic. Both debaters
receive identical evidence, so neither wins by having more information. The third
turn is what makes it a debate: the bull must concede what lands or narrow the
claim.

Impact is measured, not asserted: synthesis runs once before the debate exists
and once after, and the drafts are diffed.

```
DEBATE IMPACT
NVDA: allocation 40.0% -> 30.0%
AMD:  allocation 20.0% -> 15.0%
cash  40.0% -> 55.0%
```

### 4.6 Reflection loop

`MAX_REVISIONS = 1`. The evaluator returns `revise` when any criterion scores ≤2,
a constraint is breached, a claim is unsourced, or the draft contradicts itself.
The critique is injected into a second synthesis call under a "REVISION REQUIRED"
heading.

**The loop returns to synthesis, not to the orchestrator.** The evaluator judges
the *draft*, not the evidence gathering: a breached constraint or an unaddressed
risk is a write-up problem, and re-running five analysts would not fix it while
costing several minutes. The corollary is a real limit - if a draft is weak
because the evidence is thin, the loop cannot ask for more research. See §7.

### 4.7 RAG pipeline

```
ingest.py      SEC EDGAR → data/sec/*.html + .json
processor.py   parse, section, chunk
vector_store.py  embed (MiniLM) → Chroma, metadata: ticker, filing, date, section
retriever.py   query with ticker filter, top-k
```

Retrieved chunks carry their filing and section, which is what allows synthesis
to write `source: "10-K 2026-02-25, Item 1A"` rather than an unattributed number.

### 4.8 Memory

Three scopes:

| Scope | Mechanism | Lifetime |
|---|---|---|
| Within a run | Explicit prompt composition | The run |
| Within a session | `AgentSession` | The conversation |
| Across sessions | JSON store + `ContextProvider` | Permanent |

Storage is a JSON file per user; delivery is the framework's `ContextProvider`,
attached **only** to the conversational agent. Writes are atomic (temp file +
rename). A missing or corrupt file yields empty memory rather than an error.

Each stored recommendation carries the full `InvestmentRequest` it ran under, so
a later, different investment cannot rewrite an earlier one's parameters. The
most recent objective is offered back as a default to confirm, never silently
reused.

### 4.9 Checkpointing

Two layers:

1. **Framework** - `FileCheckpointStorage` persists workflow state.
2. **Run-level** - completed candidates and their findings, saved after each
   candidate's research and each candidate's debate.

The run id is a **hash of the request**, so re-running the same command resumes
automatically with no id to track; changing the amount or the candidates produces
a different id, which is correct - that is a new analysis. The checkpoint is
deleted on success, or a resume mechanism becomes a stale cache.

### 4.10 MCP

`src/mcp/market_server.py` is a FastMCP stdio server exposing `get_stock_price`,
`get_historical_prices` and `get_technical_indicators`. Indicators are computed
server-side so the model never does arithmetic over 250 rows - cheaper and more
accurate. Incomplete trading sessions are dropped, since a NaN close corrupts the
latest price and every trailing return.

The stdio session is held open across the whole research phase, because the
manager may call the Technical Analyst in any round.

### 4.11 A2A

`src/a2a_server.py` serves the Risk Analyst over HTTP/JSON-RPC with an agent card
at `/.well-known/agent-card.json`. `A2AExecutor` adapts between the protocol's
task/message vocabulary and `agent.run()`.

The client test never imports the agent - it asserts the module was never loaded
in its process.

### 4.12 Observability

The framework's `configure_otel_providers()` installs a tracer provider with a
batch processor wrapping an OTLP exporter. A **second span processor** is
registered on the same provider for in-process handling: a live timeline, a full
trace log, and a per-agent latency and token tally.

Buffered export is right for a dashboard; unbuffered is required for live
progress. One provider, two processors, independent of each other.

### 4.13 Failure modes

Every layer fails safe, on the principle that support systems must not take the
analysis down with them.

| Failure | Behaviour |
|---|---|
| Synthesis output malformed | Validation error fed back, one repair attempt |
| Repair also fails | Raw text printed, `None` returned, run reports cleanly |
| Evaluator unparseable | Draft kept - a broken critic cannot discard good work |
| Revision unparseable | Original draft kept |
| Memory file corrupt | Empty memory, run continues |
| Checkpoint corrupt | Fresh run; worst case is repeated work |
| Orchestration stalls | 900s timeout, message naming the likely cause, resumable |
| Tracer provider absent | Warning, run continues untraced |
| Ticker not in the corpus | Analysed without fundamentals, flagged to the user |

---

## 5. Output

### 5.1 Conversational interface

![Streamlit chat](images/ui-chat.png)

![Terminal session](images/terminal-session.png)

### 5.2 A recommendation

![Recommendation](images/recommendation.png)

Each position carries a verdict, conviction, allocation, thesis, assumptions,
evidence with named sources, key risks, and what the debate changed.

### 5.3 Debate impact

![Debate impact](images/debate-impact.png)

### 5.4 Checkpoint resume

![Checkpoint resume](images/checkpoint-resume.png)

### 5.5 Observability

![Jaeger waterfall](images/jaeger-waterfall.png)

![Span attributes](images/jaeger-span.png)

![Trace summary](images/trace-summary.png)

A full exported trace is in [`sample-trace.log`](sample-trace.log).

---

## 6. Key decisions and trade-offs

- **Debate runs outside Magentic.** The manager decides for itself what is worth
  doing; 3.3 requires a debate every run. Trade-off: less native, but guaranteed
  and three predictable calls.
- **Synthesis runs twice.** Draft before the debate, draft after, then diff.
  Trade-off: one extra large call, in exchange for the debate's effect being
  observable rather than self-reported.
- **Exactly one agent allocates.** Prevents allocation logic leaking into five
  prompts and gives constraints a single enforcement point.
- **Structured output only at the boundary.** Specialists stay prose; the schema
  makes 3.5 and 3.3 mechanically enforceable. Trade-off: a required field
  guarantees presence, not truth.
- **Prompt-level schema rather than native.** The Gemini client only extracts a
  schema from a mapping, not a Pydantic class, so the shape is spelled out in the
  prompt. Trade-off: must be kept in sync by hand.
- **Specialists' raw text, not the manager's summary.** Citations survive.
  Trade-off: a larger synthesis prompt.
- **Fundamentals get pre-fetched evidence; Technical gets live tools.** Trade-off:
  deterministic and cheap, but Fundamentals cannot ask a follow-up of the filings.
- **Per-request parameters, not a fixed user profile.** The same person can be
  cautious with savings and speculative with a punt.
- **Memory injected via `ContextProvider`, scoped to one agent.** Manual injection
  fails silently when a new call site forgets it.
- **A2A exposed but not used internally.** Inside one process it adds a hop, a
  process and a failure mode for interoperability that isn't needed.
- **Custom span processor alongside the exporter.** Live progress is impossible
  with batched export alone - a lesson learned diagnosing a phantom hang.

---

## 7. Known limitations

- **Framework workflow checkpoints are written but never read.** Resumption comes
  entirely from the run-level layer.
- **The remote Risk Analyst has never run inside the orchestrator.** The
  substitution is one line but unverified as a Magentic participant.
- **The evaluator is verified only at the extremes** (1/1/1 and 5/5/5).
  Calibration on a borderline draft is untested.
- **The reflection loop can only re-synthesise, never re-research.** A critique
  is fed back into a fresh synthesis call over the *same* findings. If a draft is
  weak because the evidence itself is thin - a candidate with no filings on file,
  say - the loop cannot fix it, because nothing sends the run back to the
  orchestrator for more research.
- **The post-debate synthesis sees its own earlier draft**, which anchors it. The
  bias suppresses observed debate impact rather than inflating it.
- **Required fields guarantee presence, not truth.** Before the debate existed,
  the model wrote a plausible `debate_resolution` describing one that never
  happened.
- **Holdings assume the user acted on the advice.** No execution confirmation.
- **Memory grows without pruning.** The recall brief is bounded; the file is not.
- **Only the ingested companies can be grounded.** Others are analysed without
  fundamentals, flagged but still answered.
- **Interrupting a run leaks the MCP subprocess** - the stdio context manager
  cannot clean up on `KeyboardInterrupt`.
- **The final two or three calls are not checkpointed.** Synthesis 2, evaluation
  and revision would be repeated after a crash.

---

## 8. Future scope

- **Cut the manager's context.** It consumed ~385k input tokens across 19 calls -
  roughly a quarter of a run - because the whole conversation is resent each
  round. The clearest cost lever, with measurements to justify it.
- **Return the retrieval tool to the Fundamentals Analyst**, so it can question
  the filings rather than work from one fixed query.
- **Wire framework checkpoint resume**, so an interrupted orchestration continues
  mid-flight.
- **Retry and backoff around model calls.** A stall currently waits out a 900s
  timeout; the timeout clarifies the failure but does not recover from it.
- **Borderline evaluator test cases**, to test calibration rather than extremes.
- **An independent post-debate synthesis** that does not see its earlier draft,
  removing anchoring from the impact measurement.
- **Automated, broader ingest**, making the grounded universe a configuration
  choice rather than whatever is on disk.
- **Route the orchestrator through A2A optionally**, proving the abstraction end
  to end.

---

## 9. Cost and performance

A two-candidate run, measured from the trace:

| Metric | Value |
|---|---|
| Wall clock | ~442s |
| Model calls | 42 |
| Input tokens | 1,391,152 |
| Output tokens | 51,582 |

| Agent | Calls | Input tokens |
|---|---|---|
| Research Manager | 19 | 384,767 |
| News & Sentiment | 2 | 95,013 |
| Risk (incl. debate) | 4 | 65,821 |
| Macro & Thesis | 2 | 50,547 |
| Technical | 2 | 48,717 |
| Synthesis | 2 | 32,061 |
| Fundamentals | 2 | 1,456 |

Guards against unbounded cost: `max_round_count=25`, `max_stall_count=3`,
`MAX_REVISIONS=1`, and checkpointing so interrupted work is never paid for twice.

Latency is dominated by provider variance, not the pipeline - individual calls
ranged from 0.98s to 196s for comparable work.

---

## 10. Testing strategy

Tests are ordered cheapest-first, so a failure is found before an expensive run.

| Test | Cost | Proves |
|---|---|---|
| `test_models.py` | free | Contracts accept valid data and reject malformed output |
| `test_memory.py` | free | Memory survives process death; per-run parameters preserved |
| `test_checkpoint.py` | free | A crash leaves resumable state; success clears it |
| `test_market_mcp.py` | free | MCP server exposes tools, returns clean data |
| `test_memory_provider.py` | 2 calls | Memory reaches the model, both scopes |
| `test_evaluator.py` | 2 calls | The critic discriminates good from bad |
| `test_synthesis.py` | 1 call | Synthesis fills the schema from findings |
| `test_technical_orchestrated.py` | ~3 calls | MCP tools work inside Magentic |
| `test_a2a.py` | 1 call | The Risk Analyst is callable across runtimes |
| `test_orchestration.py` | ~40 calls | The pipeline end to end |

---

## 11. Appendix

### 11.1 Glossary

| Term | Meaning |
|---|---|
| **Magentic** | Manager-led multi-agent orchestration pattern |
| **Span** | One timed operation in a trace, with attributes and a parent |
| **Span processor** | Framework hook called as spans start and end |
| **Exporter** | Sends spans to a backend; lives inside a processor |
| **OTLP** | OpenTelemetry's wire protocol |
| **MCP** | Model Context Protocol - how an agent consumes tools |
| **A2A** | Agent-to-Agent protocol - how an agent is consumed by others |
| **Context provider** | Framework hook that injects context before every run |
| **Agent card** | A2A discovery document describing an agent |

### 11.2 Repository layout

```
src/
├── main.py              terminal front end
├── conversation.py      conversation engine (interface-agnostic)
├── models.py            input, output and evaluation contracts
├── observability.py     OpenTelemetry wiring and trace summary
├── universe.py          which companies can be grounded
├── a2a_server.py        Risk Analyst as an A2A service
├── agents/              the eight agents
├── orchestration/       Magentic workflow, debate, synthesis, evaluation
├── memory/              long-term memory, context provider, checkpoints
├── mcp/                 market-data MCP server
├── rag/                 ingest, process, embed, retrieve
└── tools/               SEC and news tools
app.py                   Streamlit chat UI
tests/                   ten tests, cheapest first
```

### 11.3 Configuration and secrets

`.env` is gitignored; `.env.example` documents every variable with no values.
Two keys are required (`GEMINI_API_KEY`, `MARKETAUX_API_TOKEN`); the OTLP
variables are optional and the system runs fully without them. No secrets are
committed.
