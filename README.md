# QuietRelay

QuietRelay prepares a daily allocation plan for a small community organization.
It matches synthetic requests with stock and volunteer capacity, using items with
the earliest expiry first. When stock is short or no volunteer is available, it
stops and gives a coordinator the evidence needed to decide what happens next.

The repository has two working parts:

- A Strands agent that runs against a local Ollama model and a deterministic
  planning tool.
- A responsive web console that sends one synthetic fixture to the loopback
  agent, then demonstrates the review, approval, audit, and undo flow.

Neither part sends messages, spends money, or dispatches a volunteer.

## How the agent boundary works

1. The application accepts only the four expected top-level fields and rejects
   unknown fields inside every record. Source IDs are replaced with short
   per-run handles, while items and zones come from small local catalogs.
2. The deterministic planner validates record counts, units, dates, duplicate
   identifiers, and volunteer capacity. It uses first-expire, first-out stock
   ordering.
3. QuietRelay binds the validated result to a Strands tool with no arguments.
   The model cannot rewrite IDs, dates, stock counts, or capacity in its tool
   call.
4. The local model exercises the tool call, but its prose is not authoritative.
   The CLI prints the deterministic plan with an empty `external_actions` list.

```mermaid
flowchart LR
    A[Synthetic request, stock, and volunteer JSON] --> B[Strict field and size validation]
    B --> C[Deterministic FEFO planner]
    C --> D[Prevalidated no-argument Strands tool]
    D --> E[Bounded local Ollama tool exercise]
    C --> F[Authoritative allocation and review JSON]

    G[Synthetic console fixture] --> A
    F --> H[Coordinator review]
    H --> I[Local approval or undo]
    I --> J[Local activity ledger]

    J --> K[No message, payment, or real-world dispatch]
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
no-argument Strands tool in a killable child process with fixed wall-clock,
turn, and token limits, then prints the deterministic plan rather than the
model's free-form prose.

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
model digest, exercise the bound Strands tool, and load the authoritative plan.
The interface supports zone filtering, decision review, a held-stock state, an
approved oats substitute, an append-only activity ledger for the session, and
undo. Desktop and mobile use the same local state.

## Verify the repository

```bash
uv run pytest
uv run ruff check src tests scripts
cd frontend
npm run build
npm run lint
```

The Python suite covers schema rejection, privacy limits, FEFO allocation,
shortage review, volunteer capacity, the bound Strands tool, loopback origin
checks, static path safety, and the integrated plan endpoint.
