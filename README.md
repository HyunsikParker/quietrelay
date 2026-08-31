# QuietRelay

QuietRelay prepares a daily allocation plan for a small community organization.
It matches synthetic requests with stock and volunteer capacity, using items with
the earliest expiry first. When stock is short or no volunteer is available, it
stops and gives a coordinator the evidence needed to decide what happens next.

The repository has two working parts:

- A Strands agent that runs three policy-constrained tools against a local
  Ollama model and a deterministic stock-aware recovery planner.
- A responsive web console that first shows the submitted control for one
  synthetic fixture, then makes the loopback recovery delta visible alongside
  the review, approval, audit, and undo flow.

Neither part sends messages, spends money, or dispatches a volunteer.

## How the agent boundary works

1. The application accepts only the four expected top-level fields and rejects
   unknown fields inside every record. Source IDs are replaced with short
   per-run handles, while items and zones come from small local catalogs.
2. The deterministic planner validates record counts, units, dates, duplicate
   identifiers, and volunteer capacity. It stages first-expire, first-out stock,
   then commits it only after an augmenting path safely assigns volunteer
   capacity.
3. `inspect_conflicts` exposes only two allowlisted option IDs and aggregate
   counts. `select_recovery` accepts only the policy-best option, and
   `validate_recovery` independently checks stock, expiry, zone, capacity, and
   provenance.
4. The local model must complete those three tools in order, but its prose is
   ignored. The CLI prints the validated plan with an empty `external_actions`
   list.

```mermaid
flowchart LR
    A[Synthetic request, stock, and volunteer JSON] --> B[Strict field and size validation]
    B --> C[Stock-aware FEFO and augmenting-path options]
    C --> D[Inspect fixed aggregate conflicts]
    D --> E[Select one allowlisted recovery]
    E --> F[Independently validate typed constraints]
    F --> G[Authoritative allocation and review JSON]

    H[Synthetic console fixture] --> A
    G --> I[Coordinator review]
    I --> J[Local approval or undo]
    J --> K[Local activity ledger]

    K --> L[No message, payment, or real-world dispatch]
```

## Privacy and safety

The demo data contains request, lot, and volunteer IDs only. It has no names,
addresses, phone numbers, health records, financial data, or live organization
records. The parser replaces source IDs with per-run handles before planning.
Ollama is fixed to `127.0.0.1`, and the model receives the output of the
validated planner rather than the source payload.

The console keeps approvals in browser memory. Reloading the page clears them.
Its only application data request is a same-origin POST to the Python server on
numeric loopback. The server rejects non-local Host and Origin values, does not
enable CORS, caps request, response, and static-asset sizes, uses a fixed input
deadline and bounded request workers, and does not log request data.

## Run the local agent

Tested toolchain: Python 3.12.13, uv 0.11.28, and Ollama 0.32.14.

```bash
ollama pull qwen3:4b-instruct-2507-q4_K_M
OLLAMA_NO_CLOUD=1 OLLAMA_HOST=127.0.0.1:11434 ollama serve
uv sync --dev
uv run python scripts/demo_local.py
```

Run `ollama serve` in a separate terminal after the model is present. Before
inference, the script verifies the exact local model digest. It exercises the
three policy-constrained Strands tools in a killable child process with fixed
wall-clock, turn, and token limits, then prints the typed plan rather than the
model's free-form prose. The fixture demonstrates safe volunteer reassignment:
the submitted greedy control resolves one request, while the recovery plan
resolves both without changing stock policy.

## Run the integrated console

Tested toolchain: Node.js 22.23.1 and npm 10.9.8.

```bash
cd frontend
npm ci
npm run build
cd ..
uv run python scripts/serve_local.py
```

Open `http://127.0.0.1:4173`. Select **Run local agent** to verify the pinned
model digest, execute inspect, select, and validate, and load the authoritative
recovery plan. The cold-start table shows the submitted control with three safe
allocations and two local decisions. The verified recovery reassigns capacity
to show four safe allocations and one local decision, without dispatching or
sending anything.
The interface supports zone filtering, decision review, a held-stock state, an
approved oats substitute, an append-only activity ledger for the session, and
undo. Substitute availability is recalculated from the current authoritative
allocations, so a recovery that consumes stock disables an insufficient option
before approval. Desktop and mobile use the same local state.

## Verify the repository

```bash
uv run pytest
uv run ruff check src tests scripts
cd frontend
npm run build
npm run lint
```

The Python suite covers schema rejection, privacy limits, FEFO allocation,
stock-scarcity regressions, augmenting paths, multi-need and capacity stress,
the three Strands tools, loopback origin checks, static path safety, and the
integrated plan endpoint.
