# Planning assistant on the Development preview

The assistant now also works without a plan: area questions, site search and
comparison, equal-program studies, and downloadable evidence reports. See the
[general assistant guide](urban-ai-agent.md). This page focuses on saved
Development plan edits and their validation.

Updated 15 October 2026. Branch: `feat/development-simulation-context`. Preview: **http://127.0.0.1:8192/** through the existing SSH tunnel to server 156, web port 51875. Main is unchanged. No GitHub push is required to use this preview.

## Start here

1. Hard refresh the web with Ctrl+F5.
2. Open **Plans**, choose a plan, select **Development** and a parcel or saved building.
3. Click the **robot button directly below Data Layers**. The assistant shows the actual open plan, scenario and revision. English interface, same font as the map; replies follow your language.
4. Ask a question or request an edit. Building edits save directly to this isolated preview using the same validation as manual Development edits. They are reversible with the Development undo tools. An alternative request should duplicate the scenario first.
5. Jobs run asynchronously. The **Saved simulation runs** selector shows status and before/after tables. Polling does not call the model. Use **Refresh** to recover stored state after an interrupted request.
6. Enable **Allow detailed SUMO/SWMM runs** before requesting native simulation. Leave it off for quick estimates.

Example prompts:

- “Giải thích plan đang mở, công trình đã chọn và dữ liệu còn thiếu.”
- “Tạo phương án B từ phương án hiện tại. Trong B, đổi tòa nhà đang chọn thành 6 tầng; giữ footprint và công năng. Chạy quick estimate.”
- “Cho tầng 1 làm thương mại, các tầng còn lại nhà ở; giữ chiều cao các tầng.”
- “Đọc kết quả đã hoàn thành gần nhất và giải thích tác động, phần nào chưa đủ dữ liệu.”
- “Tìm tối đa 3 thửa từ 1.000 đến 10.000 m² trong vùng nghiên cứu; không giả định đó là đất trống.”
- “Chuẩn bị simulation toàn phương án, sau đó kiểm chứng biến thể tiết kiệm điện với cùng chương trình công trình.”

## Capabilities and implementation

| Capability | Tools | Actual behavior and limits |
|---|---|---|
| Read current map workspace | `workspace_read` | Server rechecks plan/revision/scenario. Reads parcel, saved building, floor overrides, types/zones. Unsaved map drafts are not treated as saved designs. |
| Open/create a plan | `plan_list`, `plan_open`, `plan_create` | Create from explicit source parcel IDs, max 6; no invented source geometry. Separate/disconnected sites may be unsupported by the simulation engine. |
| Compare design alternatives | `scenario_select`, `scenario_duplicate` | Uses the actual workspace scenarios and remapped building IDs. Reference/locked scenarios cannot be edited. |
| Edit a building | `building_save` | Same `BuildingInput`, parcel/study boundary and overlap checks as Development. Preserve unspecified geometry/use/GFA/FAR flags/overrides. New footprints must be supplied/drawn; the agent asks when missing. |
| Propose zoning | `zoning_edit` | Add/edit a type or draw/assign zones using workspace validation. These remain user proposals; no official approval is inferred. Shared-type edits requiring confirmation stay in the manual workspace. |
| Search parcels | `site_search`, `site_select` | Bounded PostGIS search by bbox, geometry area and land-use code. Ordered by area/ID, not an invented quality/vacancy score. Results can be selected through the assistant. |
| Read context | `site_context`, `source_catalog` | Same warehouse/map layer repository: source inventory, flood/price records, current Development report; nearby services when a covering installed OSM snapshot exists. No automatic new infrastructure dataset acquisition. |
| Control map | `map_control` | Requests focus/layers. Frontend checks actual layer availability and reports unavailable sources instead of claiming they are displayed. |
| Prepare/run | `simulation_prepare`, `simulation_start` | Saved plan → same Development simulation endpoint → shared worker. Detailed run dynamically prepares cached local OSM network; both states share network/background. Quick preparation can differ from native source context; read the completed run's frozen sources. |
| Explain/compare | `simulation_latest`, `simulation_results` | Import current-revision/scope saved output or read session-owned jobs. Shows unknowns, source labels and stale revision flags. Historical results remain historical after editing a plan. |
| Verify an improvement | `simulation_verify` | Freeze the same source/network once and vary only efficient fixtures, efficient equipment, storage ≥50 m³, or staggered hours ≥2 h. Compare completed pairs. Does not save these controls as map building attributes or upgrade actual infrastructure. |

## What is still assumed

- The simulation's existing-building inventory and infrastructure capacities retain their existing limits. The agent does not add the Overture/GBA baseline work another team member is doing.
- Occupancy follows Development's labelled floor-area/use assumptions. Commercial floors use Other coefficients. Excluding a physical floor from GFA does not remove its operational demand.
- Counts transferred from UIT-ADrone are a background scenario prior, not observed traffic at every selected site. OD/signals remain uncalibrated. SWMM drainage is a synthetic network, not a validated flood-depth map.
- Unknown baseline demand/capacity must not be converted to zero or a real overload claim. An incomplete-trip SUMO comparison cannot prove improvement from completed-trip delay alone.
- Nearby school locations do not establish available seats. Source coverage does not establish vacant land, ownership, legal permission, compensation or flood safety.
- No arbitrary shell, SQL, URL-fetch or file-access tool is exposed to the model. Chat sessions belong to this isolated demo; do not make the loopback preview public without the group's access controls.

## Configuration and deployment

Model: existing authorized `gpt-6-luna` configuration. API key is read by the **backend only** from ignored server `.env.development-agent.local`; it is never sent to the frontend or worker. Sessions persist in `/runtime/agent.sqlite`; jobs/plans remain in this preview's existing dedicated volume. Warehouse is still read-only.

`scripts/deploy-development-preview.py` copies only the existing model configuration from the older agent preview on server 156. It does not copy chats or mutate old preview/main containers. `--frontend-only` only rebuilds the frontend. Team PostGIS must remain attached to `urbandynamics-development-preview-data` as `team-postgis` (a team database container recreation can remove that attachment).

Budgets: 200 provider calls/day, max 8 model rounds and 12 tool calls/turn, 12 Development jobs/session, ≤24 estimated SUMO runs per normal native submission. Provider/project spending limits are configured separately. No model calls are made for status polling.

Tool calling reuses the Responses API integration, following [OpenAI function calling documentation](https://developers.openai.com/api/docs/guides/function-calling). Application code validates and executes tool calls.

## Verification

Local backend tests: `backend/tests/test_development_agent.py`; saved evidence: `test-results/development-agent-backend.xml`.

Live script `scripts/check-development-agent.py` creates a separate test plan, exercises 12 tool operations, runs screening, verifies duplicate-job reuse, imports latest results and asks Luna to explain. It verifies the user's guided plan revision is unchanged.

`scripts/check-development-agent-model.py` checks one actual Luna turn: duplicate scenario → edit only its building → prepare/run quick estimate. Verifies the original 4-floor building is preserved and the alternative has 5 floors with identical footprint.

`scripts/check-development-agent-browser.cjs` checks actual server UI: current plan context, saved session, job polling/results, before/after table, font, reload, mobile fit and page errors. Screenshots and JSON evidence are in `test-results/development-agent/` (ignored by Git).

Native solver execution is covered by the existing Development pipeline and prior completed native case. This agent change verifies routing/authorization and shared input preparation; it does not claim a newly completed full native solver benchmark.
