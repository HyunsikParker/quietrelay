# QuietRelay

QuietRelay prepares a daily allocation plan for a small community organization.
It matches synthetic requests with stock and volunteer capacity, using items with
the earliest expiry first. When stock is short or no volunteer is available, it
stops and gives a coordinator the evidence needed to decide what happens next.

The repository has two working parts:

- A Strands agent that runs three policy-constrained tools against a local
  Ollama model and a deterministic stock-aware recovery planner.
- An editable console for five synthetic requests. Change quantities, expiry
  dates, priorities, zones, and volunteer capacity, then review the new plan.
  The public page runs the deterministic tools in the browser; the local
  console runs the Strands agent. Each mode is labeled on screen.

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

    H[Editable synthetic console] --> A
    H --> M[Browser-only tool preview: no model]
    M --> I
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
The public preview makes no planning API request. In local agent mode, its only
application data request is a same-origin POST to the Python server on
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

Open `http://127.0.0.1:4173` with Ollama running. Edit the sample and select
**Run local agent**. The server verifies the pinned model, runs the three Strands
tools, and returns a typed plan. The console checks the result against the exact
submitted input before showing it.

The original sample has three ready requests in the first-fit control and four
in the recovery plan. Set rice stock to **6** and volunteer 1 capacity to **3**
to make all five requests ready. Expired stock is excluded. These are synthetic
examples, not measured outcomes from a community organization.

Select a request to inspect its allocation or shortage evidence. Ready requests
can be approved locally; unresolved requests can be marked for follow-up.
Follow-up does not reserve stock. Undo reverses a local decision. Editing any
input or running a new plan clears earlier approvals. Activity is kept in the
current tab only, with the latest 30 events visible.

After replanning, **Save review** downloads a readable text snapshot of all five
requests, their current decisions, allocation or shortage evidence, and the
input resources. Unreviewed requests stay explicitly pending. The file labels
browser preview versus local agent results and records no dispatch. It remains
available after the tab closes; subsequent edits do not update the saved file.

The [public preview](https://hyunsikparker.github.io/quietrelay/) calculates new
inputs using a browser implementation of the deterministic planning tools. It
does not run Strands or an LLM. Use `?mode=replay` on the local console to test
that same browser mode. The input editor is limited to the five-request sample;
it is not an import interface for real organization data.

## Verify the repository

After `uv sync --dev` and `npm ci` in `frontend`, run `npm --prefix frontend run
test:planner` to compare 24 frozen synthetic scenarios against the Python
planner and check rejection of stale results, over-allocation and invalid inputs.

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
