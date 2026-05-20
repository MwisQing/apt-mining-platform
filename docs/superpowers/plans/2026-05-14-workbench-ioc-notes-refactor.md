# Workbench And IOC Notes Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the workbench snapshot dependency, switch the workbench to date-scoped full-load plus frontend in-memory filtering, and fix IOC notes batch editing and save regressions.

**Architecture:** Keep candidate aggregation and decoration on the backend, but stop using snapshot tables as the workbench query source. The frontend workbench becomes the owner of filtering, sorting, searching, and paging after a date-scoped full load. IOC note workflows are unified so create/edit/batch-create all use the same normalized payload rules.

**Tech Stack:** FastAPI, SQLite, Vue 3, Element Plus, unittest, Vite

---

### Task 1: Lock regression coverage for traced note editing and candidate querying

**Files:**
- Modify: `backend/tests/test_snapshot_query_semantics.py`
- Create: `backend/tests/test_traced_api.py`
- Test: `backend/tests/test_snapshot_query_semantics.py`
- Test: `backend/tests/test_traced_api.py`

- [ ] **Step 1: Write the failing candidate query behavior test**

```python
def test_returns_candidates_without_snapshot_versions(self):
    response = self._call_query(date_start="2026-05-01", date_end="2026-05-01")
    self.assertIn("items", response)
    self.assertIn("filter_options", response)
    self.assertNotEqual(response["meta"].get("snapshot_status"), "building")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest backend.tests.test_snapshot_query_semantics -v`
Expected: FAIL because the endpoint currently returns `snapshot_status=building` with empty data when no active snapshot exists.

- [ ] **Step 3: Write the failing traced update regression tests**

```python
def test_update_traced_normalizes_empty_port_and_updates_note(self):
    ...

def test_create_traced_accepts_batch_payload(self):
    ...
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python -m unittest backend.tests.test_traced_api -v`
Expected: FAIL until traced create/update normalization and batch payload handling are implemented.

### Task 2: Remove snapshot dependency from live candidate reads

**Files:**
- Modify: `backend/api/alerts.py`
- Modify: `backend/api/events.py`
- Modify: `backend/api/tags.py`
- Modify: `backend/api/traced.py`
- Test: `backend/tests/test_snapshot_query_semantics.py`

- [ ] **Step 1: Implement live query path in `query_alert_candidates`**

Replace the snapshot-table branch with a direct `_build_where(...)` + `_query_all_candidate_items(...)` path that keeps only date range and optional target type at the backend layer, and always returns live `filter_options`.

- [ ] **Step 2: Stop save actions from triggering snapshot rebuilds**

Change invalidation helpers and traced CRUD handlers so they only clear candidate caches and do not call `request_snapshot_refresh(...)`.

- [ ] **Step 3: Run focused backend tests**

Run: `python -m unittest backend.tests.test_snapshot_query_semantics -v`
Expected: PASS with live query semantics and no `building` fallback requirement.

### Task 3: Fix traced payload normalization and batch IOC note creation

**Files:**
- Modify: `backend/api/traced.py`
- Modify: `frontend/src/views/IocNotes.vue`
- Modify: `frontend/src/views/Settings.vue`
- Test: `backend/tests/test_traced_api.py`

- [ ] **Step 1: Normalize traced payloads in backend**

Support single object or list payloads, trim `target`, normalize empty `port` to `None`, and reject duplicate update collisions cleanly.

- [ ] **Step 2: Add batch create/edit UX in `IocNotes.vue`**

Use a larger textarea for IOC lines, support one IOC per line in `target[:port]` format for create mode, keep single-entry edit mode, and reuse the same note field for batch create.

- [ ] **Step 3: Align the Settings traced-add dialog**

Allow the Settings traced add dialog to use the same normalized payload rules so the behavior matches `/ioc-notes`.

- [ ] **Step 4: Run traced API tests**

Run: `python -m unittest backend.tests.test_traced_api -v`
Expected: PASS.

### Task 4: Switch the workbench to date-scoped full load plus frontend filtering

**Files:**
- Modify: `frontend/src/views/Workbench.vue`
- Modify: `frontend/src/api/candidates.js` (if request helper needs a comment or wrapper change)
- Test: `backend/tests/test_candidate_sorting.py`

- [ ] **Step 1: Make workbench always load full date-scoped candidate data**

Set the request to always fetch the entire date-bounded candidate set, then perform `target_kind`, `hide_traced`, keyword search, exclude-tags, column filters, sorting, and paging in frontend memory.

- [ ] **Step 2: Remove snapshot-specific UI state**

Delete snapshot loading alert usage and any frontend logic that assumes snapshot status is part of the happy path.

- [ ] **Step 3: Keep device-tag edits immediately visible**

After tag add/remove, refresh the in-memory dataset and keep the current filtering logic stable.

- [ ] **Step 4: Run sort-related regression tests**

Run: `python -m unittest backend.tests.test_candidate_sorting -v`
Expected: PASS.

### Task 5: Remove import-time waiting on snapshot readiness

**Files:**
- Modify: `frontend/src/views/Settings.vue`
- Modify: `frontend/src/api/snapshots.js` (only if dead code removal is needed for build cleanliness)

- [ ] **Step 1: Remove snapshot polling after imports**

After import completion, show success based on import processing only and stop polling `/api/snapshots/status`.

- [ ] **Step 2: Clean up obsolete state and copy**

Remove `snapshotCheckStarted`, `startSnapshotCheck`, and related messages so import UX no longer implies backend post-processing is blocking the workbench.

### Task 6: Verify end-to-end and document progress

**Files:**
- Modify: `CLAUDE.md`
- Test: `backend/tests/test_snapshot_query_semantics.py`
- Test: `backend/tests/test_traced_api.py`
- Test: `backend/tests/test_candidate_sorting.py`
- Test: `frontend` build

- [ ] **Step 1: Run backend regression suite**

Run: `python -m unittest backend.tests.test_snapshot_query_semantics backend.tests.test_traced_api backend.tests.test_candidate_sorting -v`
Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run: `npm run build`
Expected: build succeeds with no Vue compile errors.

- [ ] **Step 3: Update `CLAUDE.md` progress log**

Append a new progress row describing the workbench live-query refactor, IOC notes batch entry, traced edit fix, and removal of snapshot waiting from save/import flows.
