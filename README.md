# DocSystem

Local-first document, email, ledger, reporting, and automation system.

This repository is the **authoritative definition** of how DocSystem is designed, built, and extended.
All development must follow this document.

---

## 1. Core Objective

Build a **deterministic, auditable, future-proof** system that:

- Ingests documents, emails, attachments, CSVs, scans
- Extracts structured financial and contextual data
- Maintains a **local source of truth**
- Uses Paperless only as a document UI
- Generates real-time XLSX financial reports
- Supports future unknown requirements without redesign
- Enables high-confidence querying and automation
- Runs quietly in the background with adaptive priority

---

## 2. Architectural Principle

> **Paperless is a consumer UI, not the source of truth.**

The system state lives locally and can be:
- regenerated
- reinterpreted
- re-reported
without re-ingesting raw data.

---

## 3. Folder Structure (Authoritative)

DocSystem/
├── README.md ← this file
├── data/
│ └── ledger.sqlite3 ← authoritative structured state
├── state/
│ ├── events/ ← append-only JSONL event log
│ ├── docs/ ← document sidecars
│ ├── txns/ ← transaction sidecars
│ ├── profiles/ ← import profiles (JSON)
│ └── secrets/
│ ├── ha_token.txt
│ ├── paperless_token.txt
│ └── gmail/
│ ├── client_secret.json
│ └── token.json
├── handlers/ ← ingestion & integration plugins
├── policies/ ← policy engines (FX, allocation, etc.)
├── reports/ ← report definitions
├── outputs/ ← generated XLSX files
├── Email-Archive/ ← archived raw .eml files (YYYY/MM/)


All folders under `DocSystem` are synced via Nextcloud for real-time backup.

---

## 4. Source Types (Expandable)

Current:
- Scanner → folder
- Gmail via API
- Manual file drops

Future:
- CSV exports (banks, services)
- APIs
- Other email providers
- Bulk historical imports

**Rule:**  
Each source is implemented as a **handler plugin**.  
Core logic is never modified for new sources.

---

## 5. Ingestion Layer

Responsibilities:
- Detect new input
- Identify source type
- Archive raw originals
- Emit structured ingestion events

Guarantees:
- Raw inputs are never lost
- Re-ingestion is idempotent
- Failures are logged and retryable

Example (Email):
- Raw `.eml` archived to `Email-Archive/YYYY/MM/`
- Event written to `state/events/ingest_events.jsonl`

---

## 6. Normalization & Extraction

Responsibilities:
- OCR (if required)
- Text normalization
- Structure recovery (tables, ordering)
- Key:value extraction
- Currency detection
- Confidence scoring

Output:
- Normalized text
- Structured JSON
- Extracted transactions
- Confidence metadata

**Rule:**  
Extraction produces **facts + confidence**, never assumptions.

---

## 7. State Layer (Source of Truth)

Stored in:
- `data/ledger.sqlite3`
- `state/*.jsonl` mirrors (append-only)

Contains:
- Documents
- Transactions
- Entities
- Properties
- Accounts
- Allocations
- FX decisions
- Events
- Corrections
- Policy applications

Guarantees:
- Every number is traceable to a document
- Every change is auditable
- Past data can be reinterpreted without re-ingestion

---

## 8. Paperless Integration

Purpose:
- Human browsing
- Search
- Viewing
- Limited manual correction

Contract:
- Paperless documents link back to ledger IDs
- Custom fields mirror ledger state
- Business logic never lives in Paperless

### Email Bundle Model
- Email body → PDF (parent document)
- Attachments → separate documents
- Linked via Message-ID and Parent Document ID

---

## 9. Policies (Future-Proofing)

Policies answer questions like:
- Which FX rate applies?
- How is an expense allocated?
- How are retroactive changes handled?

Rules:
- Policies are **code modules**
- YAML/JSON only selects and configures policies
- Policies can be reapplied, reversed, versioned

This enables changes in thinking **years later** without rebuilding.

---

## 10. Reporting (XLSX)

Characteristics:
- Generated from state, not Paperless
- Deterministic and fast
- Clickable links to source documents
- Regenerable at any time

Supports:
- Multiple entities
- Multiple fiscal years
- Cross-currency
- Retroactive corrections
- New report types without redesign

---

## 11. Query & Q&A Layer

Capabilities:
- Structured queries over ledger state
- Embedding-backed semantic search (when needed)
- Cited answers with confidence gating

Trust Model:
- If confidence is insufficient, system says so
- Answers are explainable and traceable

---

## 12. Automation & Detectors

Detectors observe extracted content and identify actionable situations.

Examples:
- School reminders
- Payment deadlines
- Compliance issues
- Missing data

Actions:
- Home Assistant notifications
- Calendar events
- Tasks
- Review flags

Detectors are optional plugins, not core logic.

---

## 13. Error Handling & Recovery

Built-in requirements:
- Structured error events
- Retry queues
- Partial success handling
- Manual override paths

No silent failures.

---

## 14. Performance Model

- Runs at low priority during active use
- Ramps up when idle
- Chunked workloads
- Safe to leave running continuously

---

## 15. Development Phases (Checklist)

### Phase 1 — Ingestion Foundations ✅
- Folder watcher
- Gmail ingestion
- Raw archiving
- Event logging

### Phase 2 — Email → Paperless (current)
- Render email body to PDF
- Upload email PDF
- Upload attachments
- Populate custom fields
- Label cleanup

### Phase 3 — Ledger Integration
- Document ↔ transaction linkage
- Deduplication
- Confidence scoring

### Phase 4 — Policies
- FX engine
- Allocation engine
- Retroactive reapplication

### Phase 5 — Reporting
- XLSX generation
- Real-time updates
- New report definitions

### Phase 6 — Q&A
- Structured query engine
- Embeddings
- Confidence gating

### Phase 7 — Automation
- Detector framework
- Home Assistant actions
- Domain-specific rules

---

## 16. Rules for All Future Work

- One step at a time
- No re-answering solved questions
- No silent assumptions
- Prefer unused fields over rebuilds
- Prefer reversibility over cleverness
- Paperless is not the source of truth
- State is sacred
- System must survive future changes in thinking

---

## 17. Use of Codex (Implementation Accelerator)

DocSystem deliberately separates **system design** from **code generation**.

This project uses **two distinct execution modes**, each with a strict role.

---

### 17.1 Roles and Responsibilities

#### Chat (Architecture & Control Plane)
Used for:
- Defining architecture and data ownership
- Locking contracts and invariants
- Choosing policies (FX, allocation, confidence, retroactivity)
- Identifying irreversible decisions
- Evaluating future-proofing implications
- Producing Codex-ready implementation briefs

Chat is the **architect, reviewer, and decision authority**.

Chat must be used whenever:
- A decision affects correctness, trust, or auditability
- A choice cannot be easily reversed later
- A new abstraction or policy is introduced

---

#### Codex (Execution Plane)
Used for:
- Implementing **already-locked specifications**
- Writing full files (handlers, processors, reports)
- Refactoring within frozen boundaries
- Generating large, consistent code blocks
- Implementing one phase or component at a time

Codex is the **executor**.

Codex must:
- Follow the brief literally
- Avoid inventing structure or assumptions
- Avoid changing architecture
- Avoid introducing new policies
- Produce complete, runnable code (no placeholders, no TODOs)

---

### 17.2 Mandatory Workflow

For each development phase:

1. **Chat**
   - Confirm phase scope
   - Resolve all ambiguity
   - Lock behavior and contracts
   - Produce a precise Codex brief

2. **Codex**
   - Implement exactly what is specified
   - Generate full files
   - No architectural changes

3. **Chat**
   - Review results
   - Adjust design if needed
   - Lock the next phase

Skipping this workflow is explicitly disallowed.

---

### 17.3 What Must NEVER Be Done in Codex

Codex must not:
- Choose defaults or policies
- Guess user intent
- Introduce new data ownership rules
- Change the meaning of existing fields
- Optimize in ways that reduce auditability
- Collapse future flexibility for convenience

If any of the above is required, return to **Chat** first.

---

### 17.4 Design Principle

> **Chat decides what must never be wrong.  
> Codex makes it fast.**

This separation exists to ensure:
- Long-term trust in outputs
- Compliance safety
- Reinterpretability of historical data
- Survival of future changes in thinking

---

### 17.5 Phase Suitability for Codex

Safe to fully offload to Codex:
- Handler implementations
- Email/PDF rendering
- CSV ingestion logic
- Report generators (XLSX)
- Detectors and actions (after contract is locked)

Not safe to offload to Codex:
- Architecture definition
- Policy selection
- Data model ownership decisions
- Confidence and trust thresholds

---

### 17.6 Instruction Contract

Any assistant working on DocSystem must:
- Follow this Chat ↔ Codex split
- Refuse to blur responsibilities
- Prefer reversibility over cleverness
- Prefer unused fields over rebuilds
- Preserve auditability at all times

Failure to follow this section invalidates the implementation.