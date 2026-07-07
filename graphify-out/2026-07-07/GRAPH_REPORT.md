# Graph Report - EnglishProject  (2026-07-07)

## Corpus Check
- 38 files · ~20,774 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 278 nodes · 379 edges · 62 communities (20 shown, 42 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 12 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `87174770`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Graphify Pipeline & Exports|Graphify Pipeline & Exports]]
- [[_COMMUNITY_Word CRUD & Tests|Word CRUD & Tests]]
- [[_COMMUNITY_DB Models & Routers|DB Models & Routers]]
- [[_COMMUNITY_Authentication & Users|Authentication & Users]]
- [[_COMMUNITY_App Entry & Error Handling|App Entry & Error Handling]]
- [[_COMMUNITY_Pydantic Schemas|Pydantic Schemas]]
- [[_COMMUNITY_API Integration Tests|API Integration Tests]]
- [[_COMMUNITY_Alembic Migration Env|Alembic Migration Env]]
- [[_COMMUNITY_Test Fixtures|Test Fixtures]]
- [[_COMMUNITY_Graph Analysis Outputs|Graph Analysis Outputs]]
- [[_COMMUNITY_Token Reduction Benchmark|Token Reduction Benchmark]]
- [[_COMMUNITY_Cluster-Only Rerun|Cluster-Only Rerun]]
- [[_COMMUNITY_SQLAlchemy Session|SQLAlchemy Session]]
- [[_COMMUNITY_SQLAlchemy Session|SQLAlchemy Session]]
- [[_COMMUNITY_SQLAlchemy Session|SQLAlchemy Session]]
- [[_COMMUNITY_SQLAlchemy Session|SQLAlchemy Session]]
- [[_COMMUNITY_graphify reference add a URL and watch a folder|graphify reference: add a URL and watch a folder]]
- [[_COMMUNITY_graphify reference commit hook and native CLAUDE.md integration|graphify reference: commit hook and native CLAUDE.md integration]]
- [[_COMMUNITY_graphify reference incremental update and cluster-only|graphify reference: incremental update and cluster-only]]
- [[_COMMUNITY_graphify reference GitHub clone and cross-repo merge|graphify reference: GitHub clone and cross-repo merge]]
- [[_COMMUNITY_graphify reference transcribe video and audio|graphify reference: transcribe video and audio]]
- [[_COMMUNITY_graphify|graphify]]
- [[_COMMUNITY_extraction-spec|extraction-spec.md]]
- [[_COMMUNITY_graphify add (URL ingest)|graphify add (URL ingest)]]
- [[_COMMUNITY_Folder Watcher (--watch)|Folder Watcher (--watch)]]
- [[_COMMUNITY_FalkorDB Export (Cypher)|FalkorDB Export (Cypher)]]
- [[_COMMUNITY_MCP Stdio Server|MCP Stdio Server]]
- [[_COMMUNITY_Neo4j Export (Cypher)|Neo4j Export (Cypher)]]
- [[_COMMUNITY_Confidence Score Rubric|Confidence Score Rubric]]
- [[_COMMUNITY_Hyperedges|Hyperedges]]
- [[_COMMUNITY_Node ID Format Rule|Node ID Format Rule]]
- [[_COMMUNITY_Extraction Subagent Prompt|Extraction Subagent Prompt]]
- [[_COMMUNITY_GitHub Repo Clone|GitHub Repo Clone]]
- [[_COMMUNITY_Cross-Repo Graph Merge (merge-graphs)|Cross-Repo Graph Merge (merge-graphs)]]
- [[_COMMUNITY_Native CLAUDE.md Integration|Native CLAUDE.md Integration]]
- [[_COMMUNITY_Post-Commit Auto-Rebuild Hook|Post-Commit Auto-Rebuild Hook]]
- [[_COMMUNITY_graphify explain (node explanation)|graphify explain (node explanation)]]
- [[_COMMUNITY_graphify path (shortest path)|graphify path (shortest path)]]
- [[_COMMUNITY_graphify query (BFSDFS traversal)|graphify query (BFS/DFS traversal)]]
- [[_COMMUNITY_Constrained Query Expansion|Constrained Query Expansion]]
- [[_COMMUNITY_Work Memory  Self-Improving Loop (save-result, reflect)|Work Memory / Self-Improving Loop (save-result, reflect)]]
- [[_COMMUNITY_Whisper VideoAudio Transcription|Whisper Video/Audio Transcription]]
- [[_COMMUNITY_build_merge (replace-on-re-extract)|build_merge (replace-on-re-extract)]]
- [[_COMMUNITY_Incremental Update (--update)|Incremental Update (--update)]]
- [[_COMMUNITY_Structural AST Extraction (Part A)|Structural AST Extraction (Part A)]]
- [[_COMMUNITY_Community Detection  Clustering|Community Detection / Clustering]]
- [[_COMMUNITY_File Detection (Step 2)|File Detection (Step 2)]]
- [[_COMMUNITY_God Nodes|God Nodes]]
- [[_COMMUNITY_graph.json (GraphRAG output)|graph.json (GraphRAG output)]]
- [[_COMMUNITY_GRAPH_REPORT|GRAPH_REPORT.md]]
- [[_COMMUNITY_graphify Pipeline|graphify Pipeline]]
- [[_COMMUNITY_Honesty Rules (EXTRACTEDINFERREDAMBIGUOUS audit trail)|Honesty Rules (EXTRACTED/INFERRED/AMBIGUOUS audit trail)]]
- [[_COMMUNITY_Semantic Extraction Cache|Semantic Extraction Cache]]
- [[_COMMUNITY_Semantic Extraction (Part B, subagents)|Semantic Extraction (Part B, subagents)]]
- [[_COMMUNITY_graph.json Shrink Guard (479)|graph.json Shrink Guard (#479)]]
- [[_COMMUNITY_graphify Skill Trigger (graphify)|graphify Skill Trigger (/graphify)]]
- [[_COMMUNITY_graphify Codebase-Query Convention|graphify Codebase-Query Convention]]

## God Nodes (most connected - your core abstractions)
1. `User` - 23 edges
2. `create_word()` - 12 edges
3. `get_word()` - 12 edges
4. `What You Must Do When Invoked` - 12 edges
5. `/graphify` - 10 edges
6. `generate_variants()` - 8 edges
7. `graphify reference: extra exports and benchmark` - 8 edges
8. `ai_generate_phrase()` - 7 edges
9. `get_words_by_owner()` - 6 edges
10. `generate_phrase()` - 6 edges

## Surprising Connections (you probably didn't know these)
- `test_create_word()` --calls--> `create_word()`  [EXTRACTED]
  tests/unit/test_crud_words.py → app/crud/words.py
- `test_get_word()` --calls--> `get_word()`  [EXTRACTED]
  tests/unit/test_crud_words.py → app/crud/words.py
- `test_get_word_not_found()` --calls--> `get_word()`  [EXTRACTED]
  tests/unit/test_crud_words.py → app/crud/words.py
- `test_get_word_wrong_owner()` --calls--> `get_word()`  [EXTRACTED]
  tests/unit/test_crud_words.py → app/crud/words.py
- `test_delete_word_not_found()` --calls--> `delete_word()`  [EXTRACTED]
  tests/unit/test_crud_words.py → app/crud/words.py

## Import Cycles
- None detected.

## Communities (62 total, 42 thin omitted)

### Community 0 - "Graphify Pipeline & Exports"
Cohesion: 0.29
Nodes (5): Architecture, Commands, graphify, Project overview, Testing

### Community 1 - "Word CRUD & Tests"
Cohesion: 0.13
Nodes (29): answer_word(), count_words_created_today(), create_word(), delete_word(), get_random_unlearned_word(), get_word(), get_words_by_owner(), get_words_stats() (+21 more)

### Community 2 - "DB Models & Routers"
Cohesion: 0.26
Nodes (19): User, login(), Session, register(), answer_word(), create_word(), get_random_word(), get_stats() (+11 more)

### Community 3 - "Authentication & Users"
Cohesion: 0.13
Nodes (11): authenticate_user(), create_user(), get_user_by_email(), Session, set_premium(), update_level(), UserCreate, decode_access_token() (+3 more)

### Community 4 - "App Entry & Error Handling"
Cohesion: 0.11
Nodes (25): ai_generate_phrase(), _build_prompt(), Генерация английской фразы и её русского перевода через Groq API.  Это «онлайн»-, Промпт, требующий строго JSON с английской фразой и её переводом.      scenario, Одна английская фраза со словом + её русский перевод, через Groq.      avoid — ф, _fresh_phrase(), regenerate_phrase(), _classify() (+17 more)

### Community 5 - "Pydantic Schemas"
Cohesion: 0.20
Nodes (13): update_level(), AnswerRequest, BillingStatus, Config, LevelUpdate, PaginatedWordResponse, PhrasePreviewRequest, PhrasePreviewResponse (+5 more)

### Community 6 - "API Integration Tests"
Cohesion: 0.22
Nodes (8): Тестирование поиска и фильтрации, Тестирование обработки ошибок, Тестирование пагинации, Тестирование полного потока работы с API, test_api_flow(), test_error_handling(), test_pagination(), test_search_and_filter()

### Community 7 - "Alembic Migration Env"
Cohesion: 0.25
Nodes (6): Word, Base, Режим offline: генерирует SQL-скрипт без подключения к БД., Режим online: подключается к БД и применяет миграции напрямую., run_migrations_offline(), run_migrations_online()

### Community 8 - "Test Fixtures"
Cohesion: 0.11
Nodes (13): get_db(), AppException, http_exception_handler(), validation_exception_handler(), log_requests(), read_current_user(), activate_premium(), billing_status() (+5 more)

### Community 16 - "SQLAlchemy Session"
Cohesion: 0.08
Nodes (24): For /graphify add and --watch, For /graphify query, For the commit hook and native CLAUDE.md integration, For --update and --cluster-only, /graphify, Honesty Rules, Interpreter guard for subcommands, Part A - Structural extraction for code files (+16 more)

### Community 18 - "SQLAlchemy Session"
Cohesion: 0.22
Nodes (8): graphify reference: extra exports and benchmark, Step 6b - Wiki (only if --wiki flag), Step 7 - Neo4j export (only if --neo4j or --neo4j-push flag), Step 7a - FalkorDB export (only if --falkordb or --falkordb-push flag), Step 7b - SVG export (only if --svg flag), Step 7c - GraphML export (only if --graphml flag), Step 7d - MCP server (only if --mcp flag), Step 8 - Token reduction benchmark (only if total_words > 5000)

### Community 20 - "SQLAlchemy Session"
Cohesion: 0.33
Nodes (5): For /graphify explain, For /graphify path, graphify reference: query, path, explain, Step 0 — Constrained query expansion (REQUIRED before traversal), Step 1 — Traversal

### Community 22 - "graphify reference: add a URL and watch a folder"
Cohesion: 0.50
Nodes (3): For /graphify add, For --watch, graphify reference: add a URL and watch a folder

### Community 23 - "graphify reference: commit hook and native CLAUDE.md integration"
Cohesion: 0.50
Nodes (3): For git commit hook, For native CLAUDE.md integration, graphify reference: commit hook and native CLAUDE.md integration

### Community 24 - "graphify reference: incremental update and cluster-only"
Cohesion: 0.50
Nodes (3): For --cluster-only, For --update (incremental re-extraction), graphify reference: incremental update and cluster-only

## Knowledge Gaps
- **78 isolated node(s):** `Config`, `graphify`, `Usage`, `What graphify is for`, `Step 0 - GitHub repos and multi-path merge (only if a URL or several paths)` (+73 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **42 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `User` connect `DB Models & Routers` to `Test Fixtures`, `Authentication & Users`, `Pydantic Schemas`, `Alembic Migration Env`?**
  _High betweenness centrality (0.035) - this node is a cross-community bridge._
- **Why does `create_word()` connect `Word CRUD & Tests` to `App Entry & Error Handling`, `Pydantic Schemas`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Why does `WordCreate` connect `Pydantic Schemas` to `Word CRUD & Tests`, `DB Models & Routers`?**
  _High betweenness centrality (0.027) - this node is a cross-community bridge._
- **Are the 12 inferred relationships involving `HTTPException` (e.g. with `login()` and `register()`) actually correct?**
  _`HTTPException` has 12 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Генерация английской фразы и её русского перевода через Groq API.  Это «онлайн»-`, `Промпт, требующий строго JSON с английской фразой и её переводом.      scenario`, `Одна английская фраза со словом + её русский перевод, через Groq.      avoid — ф` to the rest of the system?**
  _104 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Word CRUD & Tests` be split into smaller, more focused modules?**
  _Cohesion score 0.13333333333333333 - nodes in this community are weakly interconnected._
- **Should `Authentication & Users` be split into smaller, more focused modules?**
  _Cohesion score 0.12554112554112554 - nodes in this community are weakly interconnected._