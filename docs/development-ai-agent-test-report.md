# Development agent verification — 15 October 2026

Preview: workstation **8192** → SSH → server 156 loopback **51875**. Isolated branch `feat/development-simulation-context`; main and the previous agent preview remain separate.

| Check | Result | Evidence |
|---|---|---|
| Backend agent behavior | **9/9 passed**, 8.47 s | `test-results/development-agent-backend.xml` |
| Existing frontend result/job regression | **6/6 passed** | DevelopmentSimulation and usePlanSimulation Vitest suites |
| TypeScript and Vite production build | Passed, 2012 modules | Local build and server Compose build |
| Live API/tool flow | **12 successful operations** | `test-results/development-agent/live-result.json` |
| Real Luna read/explanation | `workspace_read` and `simulation_results` succeeded; Vietnamese explanation | Same evidence file |
| Real Luna edit/run orchestration | **7 successful tool calls**, 17.55 s | `test-results/development-agent/model-write-result.json` |
| Actual browser checks | **8 checks passed** | `test-results/development-agent/browser-result.json` |
| Chat sent from actual browser UI | Correct plan/revision/scenario sent; Luna called `workspace_read` and correctly identified Scenario A's 2-floor building | `test-results/development-agent/browser-chat.json` |
| Model key isolation | Backend has key; worker/frontend do not | Container environment presence checks, no secret values printed |

## What was exercised

The API case creates a **separate integration test plan**, loads a saved building, reads source/catalog/parcel context, finds three bounded source candidates, duplicates a scenario, changes only the copied building to four floors, prepares and runs screening, retries the same submission and verifies the same job is reused. It reads output and imports the latest completed saved run. The user's guided plan revision is checked unchanged.

The real-model write turn requests an alternative in natural language. Luna reads the current workspace, duplicates the scenario, reads the copied IDs, saves a five-floor building, reads the saved state, prepares inputs and starts a quick estimate. The original remains four floors and its geometry equals the new alternative's geometry. The resulting screening job completed successfully.

The browser regression checks the actual deployed map: open plan, assistant button/panel, current plan context, restore saved chat, poll/select a saved job and render Before/After/Change, reload session, matching computed font and 390 px mobile fit. No page errors were observed. Screenshots are under `test-results/development-agent/`.

Backend tests include stale/dirty/read-only protection, preservation of building geometry and floor overrides, scenario-copy IDs, job reuse and session ownership, stale-result flags, native opt-in, prevention of invented footprints, paired variant input equivalence, model tool loop/replay, disabled route checks and routing authorized native settings through the same Development endpoint.

## Limits of this verification

- A new full SUMO/SWMM solver benchmark was **not** run for the agent change. Native routing, authorization and shared input preparation are tested; the existing Development pipeline and completed native case provide solver evidence.
- No new real baseline/capacity dataset was acquired or wired in; that work belongs to another team member. Missing capacity/inventory remains visible as unknown.
- Real-model results show the tested prompts succeeded, not that every possible phrasing or complex planning request is guaranteed correct. The backend validates edits and the UI exposes tool traces and saved outputs for review.
- Existing city traffic/drainage assumptions remain uncalibrated. This integration does not convert model estimates into observed forecasts or planning approval.
