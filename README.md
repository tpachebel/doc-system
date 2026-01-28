# DocSystem

**Local-first document, transaction, and automation system**  
Deterministic • Auditable • Future-proof

This repository is the **authoritative specification** for DocSystem.  
All implementation **must conform to this document**.

---

## 1. Core Objective

Build a system that:

- Ingests documents, emails, attachments, scans, CSVs, and feeds

- Extracts structured facts with confidence and evidence

- Maintains a **local, regenerable source of truth**

- Treats Paperless as a **consumer UI only**

- Produces deterministic financial reports

- Enables high-confidence querying and automation

- Survives future changes in thinking without redesign

---

## 2. Architectural Principle

> **Paperless is a UI.  
> DocSystem is the source of truth.**

All meaning lives locally and can be:

- re-extracted

- reinterpreted

- re-linked

- re-reported

without re-ingesting raw inputs.

---

## 3. Authoritative Folder Structure

DocSystem/ 

├── README.md                     ← this file 

├── data/ 

│   └── ledger.sqlite3            ← authoritative structured state 

├── state/ 

│   ├── events/               ← append-only JSONL event log 

│   ├── docs/                 ← document sidecars 

│   ├── txns/                 ← transaction sidecars 

│   ├── profiles/             ← import/source profiles 

│   └── secrets/ 

│       ├── ha_token.txt 

│       ├── paperless_token.txt 

│       └── gmail/ 

│           ├── client_secret.json 

│           └── token.json 

├── handlers/                 ← ingestion plugins 

├── policies/                 ← policy engines (future) 

├── reports/                  ← report definitions 

├── outputs/                  ← generated XLSX outputs 

├── Email-Archive/            ← archived raw .eml (YYYY/MM/)

All folders are synced via Nextcloud.

---

## 4. Source Types (Expandable)

**Current**

- Scanner → folder

- Gmail via API

- Manual file drops

**Future**

- CSV exports

- Financial feeds (e.g. SimpleFin)

- APIs

- Bulk historical imports

**Rule:**  
Each source is implemented as a **handler plugin**.  
Core logic is never modified to add sources.

---

## 5. Ingestion Layer

Responsibilities:

- Detect new input

- Identify source

- Archive raw originals

- Emit ingestion events

Guarantees:

- Raw inputs are never lost

- Re-ingestion is idempotent

- Failures are logged and retryable

---

## 6. Document Model (Phase 3.1 — LOCKED)

### 6.1 Document Identity

Each document has:

- `document_id` (stable, internal)

- `source_fingerprint` (dedup detection)

- `kind` (what it fundamentally is)

- `roles[]` (how it can be used)

- `entity_id` (nullable)

- `entity_candidates[]` (optional)

Examples of `kind`:

- email_body

- attachment

- scan

- photo

- receipt

- lease

- bank_statement

- csv

- reference

Examples of `roles`:

- financial

- legal

- evidence

- personal

- warranty

- medical

Unknown entity is explicitly allowed.

---

### 6.2 Document Sidecars

Each document produces a sidecar at:

`state/docs/<document_id>.json`

Sidecars contain **facts, not decisions**.

They may include:

- extracted fields

- clauses

- line items

- normalized text

- structured JSON

- OCR outputs

Each extracted element stores:

- value

- confidence

- evidence (page, snippet, bounding box if available)

Sidecars are:

- versioned

- append-only

- regenerable

---

### 6.3 Relationships (Critical)

Relationships are **first-class, many-to-many, polymorphic records**.

They may link:

- document ↔ document

- document ↔ entity

- document ↔ property

- document ↔ unit

- document ↔ transaction

- document ↔ policy reference

A document may have **unlimited relationships**.

Relationship types are generic:

- `parent_of`

- `derived_from`

- `evidence_for`

- `covers`

- `applies_to`

- `related_to`

No business logic is encoded in relationship names.

---

## 7. Normalization & Extraction

Responsibilities:

- OCR (if required)

- Text normalization

- Structure recovery

- Key/value extraction

- Currency detection

- Confidence scoring

**Rule:**  
Extraction produces **facts + confidence + evidence**, never assumptions.

---

## 8. State Layer (Source of Truth)

Stored in:

- `data/ledger.sqlite3`

- `state/*.jsonl` mirrors

Contains:

- Documents

- Transactions

- Entities

- Properties

- Units

- Relationships

- Events

- Corrections

Guarantees:

- Every number is traceable

- Every change is auditable

- Past data can be reinterpreted

---

## 9. Paperless Integration

Purpose:

- Browsing

- Search

- Viewing

- Light manual correction

Contract:

- Paperless stores `ledger_document_id`

- Parent/child email bundles preserved

- No business logic lives in Paperless

---

## 10. Policies (Future)

Policies answer questions like:

- Which FX rate applies?

- How is rent allocated?

- How are late fees calculated?

- How are retroactive changes handled?

Policies:

- are code modules

- are selectable/configurable via YAML/JSON

- can be reapplied or reversed

---

## 11. Reporting

Reports:

- are generated from ledger state

- are deterministic

- are regenerable

- link back to source documents

---

## 12. Query & Q&A

Capabilities:

- Structured queries

- Semantic search when needed

- Confidence-gated answers

- Full citation back to evidence

If confidence is insufficient, the system must say so.

---

## 13. Automation & Detectors

Detectors:

- observe ledger state

- identify actionable situations

Examples:

- late rent

- missing payments

- upcoming deadlines

- unreimbursed medical claims

Actions:

- notifications

- emails

- tasks

- review flags

Detectors are plugins, not core logic.

---

## 14. Performance Model

- Low priority during active use

- Scales up when idle

- Chunked workloads

- Safe to run continuously

---

## 15. Development Phases

### Phase 1 — Ingestion Foundations ✅

### Phase 2 — Email → Paperless ✅

### Phase 3 — Ledger Integration

- Document identity & sidecars ✅ (locked)

- Transaction linkage

- Deduplication

- Confidence handling

### Phase 4 — Policies

### Phase 5 — Reporting

### Phase 6 — Q&A

### Phase 7 — Automation

---

## 16. Rules for All Work

- One step at a time

- No silent assumptions

- Prefer reversibility over cleverness

- Prefer unused fields over rebuilds

- State is sacred

- Paperless is not the source of truth

---

## 17. Chat ↔ Codex Workflow (Mandatory)

**Chat**

- Decides architecture

- Locks contracts

- Resolves ambiguity

**Codex**

- Implements locked specs

- Produces full files

- Makes no architectural decisions

Skipping this split is disallowed.

---

## 18. Design Principle

> **Chat decides what must never be wrong.  
> Codex makes it fast.**

---

### ✅ READY STATE

This README now fully supports:

- leases

- photos

- CSV feeds

- warranties

- reimbursements

- automation

- AI-assisted extraction

- future unknown requirements

without redesign.