# Graph Report - .  (2026-07-05)

## Corpus Check
- Corpus is ~15,335 words - fits in a single context window. You may not need a graph.

## Summary
- 160 nodes · 196 edges · 22 communities (15 shown, 7 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 25 edges (avg confidence: 0.86)
- Token cost: 69,971 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Graphify Pipeline & Exports|Graphify Pipeline & Exports]]
- [[_COMMUNITY_Word CRUD & Tests|Word CRUD & Tests]]
- [[_COMMUNITY_DB Models & Routers|DB Models & Routers]]
- [[_COMMUNITY_Authentication & Users|Authentication & Users]]
- [[_COMMUNITY_App Entry & Error Handling|App Entry & Error Handling]]
- [[_COMMUNITY_Pydantic Schemas|Pydantic Schemas]]
- [[_COMMUNITY_API Integration Tests|API Integration Tests]]
- [[_COMMUNITY_Alembic Migration Env|Alembic Migration Env]]
- [[_COMMUNITY_Graph Analysis Outputs|Graph Analysis Outputs]]
- [[_COMMUNITY_Token Reduction Benchmark|Token Reduction Benchmark]]
- [[_COMMUNITY_Cluster-Only Rerun|Cluster-Only Rerun]]
- [[_COMMUNITY_SQLAlchemy Session|SQLAlchemy Session]]
- [[_COMMUNITY_SQLAlchemy Session|SQLAlchemy Session]]
- [[_COMMUNITY_SQLAlchemy Session|SQLAlchemy Session]]
- [[_COMMUNITY_SQLAlchemy Session|SQLAlchemy Session]]
- [[_COMMUNITY_SQLAlchemy Session|SQLAlchemy Session]]

## God Nodes (most connected - your core abstractions)
1. `create_word()` - 9 edges
2. `graph.json (GraphRAG output)` - 9 edges
3. `get_word()` - 8 edges
4. `graphify Codebase-Query Convention` - 7 edges
5. `get_words_by_owner()` - 5 edges
6. `Structural AST Extraction (Part A)` - 5 edges
7. `Semantic Extraction (Part B, subagents)` - 5 edges
8. `Extraction Subagent Prompt` - 5 edges
9. `graphify query (BFS/DFS traversal)` - 5 edges
10. `Incremental Update (--update)` - 5 edges

## Surprising Connections (you probably didn't know these)
- `Native CLAUDE.md Integration` --conceptually_related_to--> `graphify Codebase-Query Convention`  [INFERRED]
  .claude/skills/graphify/references/hooks.md → CLAUDE.md
- `test_create_word()` --calls--> `create_word()`  [EXTRACTED]
  tests/unit/test_crud_words.py → app/crud/words.py
- `test_get_word()` --calls--> `get_word()`  [EXTRACTED]
  tests/unit/test_crud_words.py → app/crud/words.py
- `test_get_word_not_found()` --calls--> `get_word()`  [EXTRACTED]
  tests/unit/test_crud_words.py → app/crud/words.py
- `test_get_word_wrong_owner()` --calls--> `get_word()`  [EXTRACTED]
  tests/unit/test_crud_words.py → app/crud/words.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **graphify Build Pipeline (detect → extract → cluster → outputs)** — _claude_skills_graphify_skill_detect, _claude_skills_graphify_skill_ast_extraction, _claude_skills_graphify_skill_semantic_extraction, _claude_skills_graphify_skill_community_detection, _claude_skills_graphify_skill_graph_json [EXTRACTED 0.85]
- **graphify Query Surface (query / path / explain)** — _claude_skills_graphify_references_query_query, _claude_skills_graphify_references_query_path, _claude_skills_graphify_references_query_explain [EXTRACTED 0.85]
- **Graph Database Exports (Neo4j / FalkorDB / MCP)** — _claude_skills_graphify_references_exports_neo4j_export, _claude_skills_graphify_references_exports_falkordb_export, _claude_skills_graphify_references_exports_mcp_server [INFERRED 0.75]

## Communities (22 total, 7 thin omitted)

### Community 0 - "Graphify Pipeline & Exports"
Cohesion: 0.08
Nodes (32): graphify add (URL ingest), Folder Watcher (--watch), FalkorDB Export (Cypher), MCP Stdio Server, Neo4j Export (Cypher), Confidence Score Rubric, Hyperedges, Node ID Format Rule (+24 more)

### Community 1 - "Word CRUD & Tests"
Cohesion: 0.15
Nodes (25): create_word(), delete_word(), get_random_unlearned_word(), get_word(), get_words_by_owner(), get_words_stats(), review_word(), toggle_learned() (+17 more)

### Community 2 - "DB Models & Routers"
Cohesion: 0.13
Nodes (12): Base, HTTPException, User, Word, login(), register(), get_random_word(), read_word() (+4 more)

### Community 3 - "Authentication & Users"
Cohesion: 0.14
Nodes (7): decode_access_token(), get_current_user(), verify_password(), authenticate_user(), create_user(), get_user_by_email(), test_login_user()

### Community 4 - "App Entry & Error Handling"
Cohesion: 0.15
Nodes (6): AppException, http_exception_handler(), validation_exception_handler(), log_requests(), Request, RequestValidationError

### Community 5 - "Pydantic Schemas"
Cohesion: 0.27
Nodes (8): BaseModel, Config, PaginatedWordResponse, UserCreate, UserResponse, WordCreate, WordLearnedUpdate, WordResponse

### Community 6 - "API Integration Tests"
Cohesion: 0.22
Nodes (8): Тестирование поиска и фильтрации, Тестирование обработки ошибок, Тестирование пагинации, Тестирование полного потока работы с API, test_api_flow(), test_error_handling(), test_pagination(), test_search_and_filter()

### Community 7 - "Alembic Migration Env"
Cohesion: 0.40
Nodes (4): Режим offline: генерирует SQL-скрипт без подключения к БД., Режим online: подключается к БД и применяет миграции напрямую., run_migrations_offline(), run_migrations_online()

### Community 9 - "Graph Analysis Outputs"
Cohesion: 0.50
Nodes (4): Wiki Export (--wiki), Community Detection / Clustering, God Nodes, GRAPH_REPORT.md

## Knowledge Gaps
- **15 isolated node(s):** `Config`, `EnglishProject FastAPI Backend`, `graphify Skill Trigger (/graphify)`, `Semantic Extraction Cache`, `God Nodes` (+10 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `update_learned()` connect `DB Models & Routers` to `Pydantic Schemas`?**
  _High betweenness centrality (0.041) - this node is a cross-community bridge._
- **Why does `WordLearnedUpdate` connect `Pydantic Schemas` to `DB Models & Routers`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Why does `test_login_user()` connect `Authentication & Users` to `Pydantic Schemas`?**
  _High betweenness centrality (0.034) - this node is a cross-community bridge._
- **Are the 8 inferred relationships involving `HTTPException` (e.g. with `get_current_user()` and `login()`) actually correct?**
  _`HTTPException` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `graph.json (GraphRAG output)` (e.g. with `Neo4j Export (Cypher)` and `Cross-Repo Graph Merge (merge-graphs)`) actually correct?**
  _`graph.json (GraphRAG output)` has 5 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Config`, `Режим offline: генерирует SQL-скрипт без подключения к БД.`, `Режим online: подключается к БД и применяет миграции напрямую.` to the rest of the system?**
  _24 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Graphify Pipeline & Exports` be split into smaller, more focused modules?**
  _Cohesion score 0.08064516129032258 - nodes in this community are weakly interconnected._