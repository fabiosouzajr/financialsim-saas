# Graph Report - .  (2026-05-29)

## Corpus Check
- 98 files · ~112,194 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 455 nodes · 701 edges · 38 communities (22 shown, 16 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 63 edges (avg confidence: 0.88)
- Token cost: 78,500 input · 11,700 output

## Community Hubs (Navigation)
- [[_COMMUNITY_UIUX Design Skill|UI/UX Design Skill]]
- [[_COMMUNITY_SaaS Feature Services|SaaS Feature Services]]
- [[_COMMUNITY_OpenWolf Hook Engine|OpenWolf Hook Engine]]
- [[_COMMUNITY_OpenWolf Cron Config|OpenWolf Cron Config]]
- [[_COMMUNITY_Financial App Docs|Financial App Docs]]
- [[_COMMUNITY_Agent Session Management|Agent Session Management]]
- [[_COMMUNITY_Kraken Design System|Kraken Design System]]
- [[_COMMUNITY_Code Architecture Skills|Code Architecture Skills]]
- [[_COMMUNITY_OpenWolf Protocol Docs|OpenWolf Protocol Docs]]
- [[_COMMUNITY_Agent Workflow Conventions|Agent Workflow Conventions]]
- [[_COMMUNITY_Session Telemetry|Session Telemetry]]
- [[_COMMUNITY_README Templates|README Templates]]
- [[_COMMUNITY_README Methodology|README Methodology]]
- [[_COMMUNITY_Claude Hook Events|Claude Hook Events]]
- [[_COMMUNITY_Cron Scheduler State|Cron Scheduler State]]
- [[_COMMUNITY_Design QC Reports|Design QC Reports]]
- [[_COMMUNITY_Local Permissions Config|Local Permissions Config]]
- [[_COMMUNITY_Pending Feature Backlog|Pending Feature Backlog]]
- [[_COMMUNITY_Search CLI|Search CLI]]
- [[_COMMUNITY_Bug Log Tracking|Bug Log Tracking]]
- [[_COMMUNITY_Cron Task Registry|Cron Task Registry]]
- [[_COMMUNITY_Linux Installation|Linux Installation]]
- [[_COMMUNITY_Post-Install Setup|Post-Install Setup]]
- [[_COMMUNITY_UI Polish Plan|UI Polish Plan]]
- [[_COMMUNITY_NPM Package Config|NPM Package Config]]
- [[_COMMUNITY_Design QC Report|Design QC Report]]
- [[_COMMUNITY_OpenWolf Config|OpenWolf Config]]
- [[_COMMUNITY_Local Settings|Local Settings]]
- [[_COMMUNITY_Windows Installation|Windows Installation]]
- [[_COMMUNITY_macOS Installation|macOS Installation]]
- [[_COMMUNITY_Antivirus Troubleshooting|Antivirus Troubleshooting]]
- [[_COMMUNITY_Login Authentication|Login Authentication]]
- [[_COMMUNITY_Multi-Context Docs|Multi-Context Docs]]

## God Nodes (most connected - your core abstractions)
1. `OpenWolf Reframe UI Framework Knowledge Base` - 16 edges
2. `main()` - 15 edges
3. `getWolfDir()` - 14 edges
4. `ensureWolfDir()` - 14 edges
5. `readJSON()` - 14 edges
6. `FinacialSim SaaS Master Roadmap` - 14 edges
7. `writeJSON()` - 12 edges
8. `Plan: Phase 4 Services Orchestration Layer` - 12 edges
9. `OpenWolf Operating Protocol` - 12 edges
10. `Architecture Vocabulary (LANGUAGE.md)` - 12 edges

## Surprising Connections (you probably didn't know these)
- `UI/UX Pro Max Design System Persist Pattern` --implements--> `FinancialSim Design System Master File`  [INFERRED]
  .claude/skills/ui-ux-pro-max/SKILL.md → design-system/financialsim/MASTER.md
- `OpenWolf Design QC Protocol` --conceptually_related_to--> `UI/UX Pro Max Skill`  [INFERRED]
  .wolf/OPENWOLF.md → .claude/skills/ui-ux-pro-max/SKILL.md
- `CLAUDE.md Project Configuration` --references--> `Domain Docs: CONTEXT.md + docs/adr/ single-context layout`  [EXTRACTED]
  CLAUDE.md → docs/agents/domain.md
- `CLAUDE.md Project Configuration` --references--> `Triage Labels: needs-triage needs-info ready-for-agent ready-for-human wontfix`  [EXTRACTED]
  CLAUDE.md → docs/agents/triage-labels.md
- `CLAUDE.md Project Configuration` --references--> `Issue Tracker: GitHub Issues via gh CLI conventions`  [EXTRACTED]
  CLAUDE.md → docs/agents/issue-tracker.md

## Communities (38 total, 16 thin omitted)

### Community 0 - "UI/UX Design Skill"
Cohesion: 0.05
Nodes (43): BM25, CSV_CONFIG (domain-to-file map), detect_domain(), _load_csv(), Lowercase, split, remove punctuation, filter short words, Build BM25 index from documents, Score all documents against query, Load CSV and return list of dicts (+35 more)

### Community 1 - "SaaS Feature Services"
Cohesion: 0.08
Nodes (49): ARQ Worker (Redis-based), Audit Log, Business Rules (business_rules table), CarneService, Customer Portal (/portal), UI Error Handler (handle_unexpected), finacialsim_core (Vendored Package), FIPE Provider Chain (+41 more)

### Community 2 - "OpenWolf Hook Engine"
Cohesion: 0.18
Nodes (34): main(), autoDetectBugFix(), detectFixPattern(), extractCalls(), extractChangedLines(), extractCSSProps(), findOperatorChange(), main() (+26 more)

### Community 3 - "OpenWolf Cron Config"
Cohesion: 0.05
Nodes (39): auto_scan_on_init, exclude_patterns, max_description_length, max_files, rescan_interval_hours, max_tokens, reflection_frequency, api_key_env (+31 more)

### Community 4 - "Financial App Docs"
Cohesion: 0.08
Nodes (39): Architecture Key Files: main price_table cet simulation_service proposta, User Guide: Early Amortization reduce-parcela or reduce-prazo, User Guide: SELIC CDI IPCA BACEN indicators tab, User Guide: PDF Proposal Generation Contents, User Guide: Simulation Flow with IOF extras PDF, CET Calculation via TIR/IRR using Brent Method, Extras Costs: mensal_continuo rateio_meses unico_inicial, IOF Calculation (Decreto 6.306/2007): fixo + diario iterative (+31 more)

### Community 5 - "Agent Session Management"
Cohesion: 0.1
Nodes (32): Claude Project Settings, Session State File, Post-Read Hook, autoDetectBugFix(), Post-Write Hook, Pre-Read Hook, checkBugLog(), checkCerebrum() (+24 more)

### Community 6 - "Kraken Design System"
Cohesion: 0.07
Nodes (33): Kraken Button Components, Kraken Color Palette, Kraken Dual Font System, Kraken Purple Brand Color, Kraken Layout Principles, Kraken Design System Overview, Kraken Typography System, FinancialSim Anti-Patterns (+25 more)

### Community 7 - "Code Architecture Skills"
Cohesion: 0.1
Nodes (32): Grill Me Skill, Deepening (Module Consolidation), Dependency Categories for Deepening, Seam Discipline (Two Adapters Rule), Replace-Not-Layer Testing Strategy, Candidate Card (Architecture Report), Diagram Patterns (Mermaid + Hand-built), Architecture HTML Report Format (+24 more)

### Community 8 - "OpenWolf Protocol Docs"
Cohesion: 0.1
Nodes (28): OpenWolf Anatomy File, OpenWolf Cerebrum Learning Memory, Claude Rules OpenWolf Configuration, OpenWolf Identity File, OpenWolf Memory Log, OpenWolf Bug Logging Protocol, OpenWolf Cerebrum Learning Protocol, OpenWolf Code Generation Protocol (+20 more)

### Community 9 - "Agent Workflow Conventions"
Cohesion: 0.12
Nodes (16): Domain Docs: CONTEXT.md + docs/adr/ single-context layout, Issue Tracker: GitHub Issues via gh CLI conventions, Triage Labels: needs-triage needs-info ready-for-agent ready-for-human wontfix, Alembic in frozen EXE: use Python API not subprocess, OpenWolf Context Management Protocol, CLAUDE.md Project Configuration, Project Structure: core data integrations services ui reports, PyInstaller Gotcha: entry point and spec paths (+8 more)

### Community 10 - "Session Telemetry"
Cohesion: 0.18
Nodes (10): anatomy_hits, anatomy_misses, cerebrum_warnings, edit_counts, files_read, files_written, repeated_reads_warned, session_id (+2 more)

### Community 11 - "README Templates"
Cohesion: 0.27
Nodes (10): README Project Types, Effective READMEs Skill README, README Section Checklist, README Style Guide, Internal README Template, OSS README Template, Personal README Template, XDG Config README Template (+2 more)

### Community 12 - "README Methodology"
Cohesion: 0.22
Nodes (10): Art of README, Cognitive Funneling, common-readme, README Checklist, Make a README, README Sections Guidelines, Maximal Standard README Example, Minimal Standard README Example (+2 more)

### Community 13 - "Claude Hook Events"
Cohesion: 0.33
Nodes (5): hooks, PostToolUse, PreToolUse, SessionStart, Stop

### Community 14 - "Cron Scheduler State"
Cohesion: 0.33
Nodes (5): dead_letter_queue, engine_status, execution_log, last_heartbeat, upcoming

### Community 15 - "Design QC Reports"
Cohesion: 0.4
Nodes (4): captured_at, captures, estimated_tokens, total_size_kb

### Community 17 - "Pending Feature Backlog"
Cohesion: 0.67
Nodes (3): TODO: IPVA percentage and emplacamento fixed fee by vehicle type, TODO: Primary Goals multi-profile simulator bank-grade CCB vehicles, TODO: Implement veiculos page with FIPE data cor placa odometro

## Knowledge Gaps
- **184 isolated node(s):** `version`, `bugs`, `last_heartbeat`, `engine_status`, `execution_log` (+179 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **16 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `UI/UX Pro Max Skill` connect `Kraken Design System` to `OpenWolf Protocol Docs`?**
  _High betweenness centrality (0.010) - this node is a cross-community bridge._
- **Why does `OpenWolf Design QC Protocol` connect `OpenWolf Protocol Docs` to `Kraken Design System`?**
  _High betweenness centrality (0.009) - this node is a cross-community bridge._
- **What connects `version`, `bugs`, `last_heartbeat` to the rest of the system?**
  _184 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `UI/UX Design Skill` be split into smaller, more focused modules?**
  _Cohesion score 0.05 - nodes in this community are weakly interconnected._
- **Should `SaaS Feature Services` be split into smaller, more focused modules?**
  _Cohesion score 0.08 - nodes in this community are weakly interconnected._
- **Should `OpenWolf Cron Config` be split into smaller, more focused modules?**
  _Cohesion score 0.05 - nodes in this community are weakly interconnected._
- **Should `Financial App Docs` be split into smaller, more focused modules?**
  _Cohesion score 0.08 - nodes in this community are weakly interconnected._