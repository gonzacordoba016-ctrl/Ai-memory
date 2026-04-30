# AUDIT.md — Stratum / ai-memory-engine
> Auditoría completa: FASE 1 (Arquitectura) + FASE 2 (Dominios) + FASE 3 (Transversales). Fecha: 2026-04-30.

---

## Totales

| Dominio | ALTO | MEDIO | BAJO |
|---|---|---|---|
| CORE | 3 | 6 | 14 |
| DATA | 5 | 8 | 4 |
| AGENT | 5 | 7 | 4 |
| INFRA | 3 | 5 | 4 |
| QA | 7 | 8 | 4 |
| MOBILE | 3 | 4 | 2 |
| CROSS | 7 | 10 | 8 |
| **TOTAL** | **33** | **48** | **40** |

### Top 5 — acción inmediata antes del próximo deploy

1. **`core/config.py:134`** — JWT_SECRET con default conocido → tokens forgeables con `MULTI_USER=true`
2. **`api/routers/`** — 110 endpoints sin `Depends(get_current_user)` → API pública en modo multi-usuario
3. **`graph_memory.py:57`** — escritura no atómica del grafo → corrupción de datos en crash
4. **`agent_controller.py:106`** — `orchestrator.run()` sin timeout → WebSocket colgado indefinidamente
5. **`stratum-mobile/android/app/google-services.json`** — credenciales Firebase commiteadas → rotar ahora

---

## PARTE 1 — ARQUITECTURA

### Stack

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.11 |
| HTTP server | FastAPI + uvicorn |
| HTTP client | httpx (requests eliminado) |
| LLM | OpenRouter (gpt-4o-mini fast · gpt-4o smart) / Ollama / LMStudio |
| Memoria SQL | SQLite WAL — `database/sql_memory.py` (singleton `_default`) |
| Memoria vectorial | Qdrant Cloud (`QDRANT_URL`) o local (`VECTOR_DB_PATH`) |
| Memoria grafo | NetworkX → `data/graph_memory.json` |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 (384 dims) |
| Render EDA | svgwrite + Three.js |
| Auth | JWT (python-jose + passlib) — flag `MULTI_USER` |
| Rate limiting | slowapi |
| Deploy | Docker (python:3.11-slim) → Railway |
| Frontend web | HTML + CSS + JS plain modules |
| Frontend mobile | Capacitor 6 → Android (`stratum-mobile/`) |

### Entrypoint

```
run.py serve  →  uvicorn api/server.py:app  →  FastAPI
run.py <cmd>  →  cli/{backup,reset,setup,status}.py
```

### Flujo principal (WebSocket → respuesta)

```
Browser/Mobile WS
  └─► api/routers/websockets.py
        └─► agent/agent_controller.py::process_input()
              ├─► agent/orchestrator.py  (routing keywords/regex)
              │     ├─► circuit_agent     (netlist + DRC + render)
              │     ├─► hardware_agent    (firmware gen/flash)
              │     ├─► memory_agent      (CRUD memoria)
              │     ├─► electrical_calc   (fórmulas Python puras)
              │     ├─► code_agent
              │     └─► research_agent
              ├─► memory/* (store episode, facts, vector search)
              └─► token streaming → WS → cliente
```

### Responsabilidad de carpetas

| Carpeta | Capa | Rol |
|---|---|---|
| `core/` | 0 | config, logger, prompt_builder — sin deps internas |
| `llm/` | 1 | async_client (httpx pool), cache (SemanticCache), openrouter_client |
| `infrastructure/` | 1 | vector_store.py — cliente Qdrant singleton |
| `database/` | 2 | Managers SQLite por dominio |
| `memory/` | 3 | vector_memory, graph_memory, fact_extractor, consolidator |
| `knowledge/` | 3 | knowledge_base.py — indexa conocimiento técnico |
| `knowledge_feed/` | datos | 8 .txt de electrónica — input de knowledge_base |
| `tools/` | 3 | renderers, DRC, formulas, firmware, KiCad exporters |
| `agent/` | 4 | orchestrator, agent_controller, agentes, proactive_engine |
| `api/` | 5 | server.py + 16 routers + auth + job_worker |
| `cli/` | 6 | backup, reset, setup, status |
| `run.py` | 6 | entrypoint único |
| `agent_files/` | output | archivos generados, no código |
| `stratum-mobile/` | subproyecto | App Capacitor/Android independiente |
| `data/`, `memory_db/` | runtime | SQLite y Qdrant en runtime |

### Routers activos (16)
`auth`, `memory`, `hardware`, `hardware_bridge`, `knowledge`, `circuits`, `circuits-public`, `websockets`, `intelligence`, `push`, `schematics`, `stock`, `decisions`, `calc`, `projects`, `hardware_state`

---

## PARTE 2 — DOMINIOS

### DOMINIO: CORE (`core/`, `api/`, `cli/`, `run.py`)
> 3 ALTO / 6 MEDIO / 14 BAJO

**[ALTO]** `api/routers/` — 0 endpoints con `Depends(get_current_user)` (110 endpoints sin protección)
- Impacto: con `MULTI_USER=true`, toda la API es pública — cualquier cliente sin token accede a memoria, circuitos, stock
- Fix: aplicar en `server.py` al incluir routers sensibles:
  ```python
  app.include_router(memory.router, dependencies=[Depends(get_current_user)])
  ```

**[ALTO]** `api/server.py:69` — CORS fallback silencioso a `["*"]` si falla import de `core.config`
- Impacto: el servidor arranca con wildcard CORS sin ningún log de error visible
- Fix: el fallback debe ser `[]` (bloquear todo) y agregar `logger.error(...)` explícito

**[ALTO]** `api/server.py`, `api/routers/hardware.py`, `cli/utils.py`, `run.py` — 16 sitios con `os.getenv()` directo sin `_env()`
- Impacto: en Railway donde env vars pueden tener comillas, `int(os.getenv("PORT", "8000"))` con `PORT="8000"` lanza `ValueError`
- Fix: reemplazar por `_env()` de `core/config.py` en todos los sitios afectados

**[MEDIO]** `api/auth.py` — `get_current_user` retorna `"default"` cuando `MULTI_USER=false` sin warning
- Fix: loguear `WARNING` en startup si auth está deshabilitado

**[MEDIO]** `api/routers/memory.py` — `except Exception: pass` silencioso en `/api/search`
- Fix: loguear el error y retornar 500 con mensaje

**[MEDIO]** `cli/backup.py`, `cli/reset.py`, `cli/status.py` — lazy imports dentro de funciones (incumple fix v4.11)
- Fix: mover imports al top del módulo

---

### DOMINIO: DATA (`database/`, `memory/`, `knowledge/`)
> 5 ALTO / 8 MEDIO / 4 BAJO

**[ALTO]** `database/intelligence.py:53` — `_init_tables()` sin `try/finally` → connection leak en error
- Fix: `with sqlite3.connect(DB_PATH) as conn:` en todos los métodos (5 afectados: `_init_tables`, `create_profile`, `update_profile`, `create_source`, `mark_indexed`, `delete_source`)

**[ALTO]** `database/intelligence.py:173,191,272,287,297` — 5 métodos abren conexión sin context manager
- Fix: reemplazar `conn = self._conn()` + manual `.close()` por `with self._conn() as conn:`

**[ALTO]** `memory/graph_memory.py:19` — singleton `__new__` sin `threading.Lock`
- Impacto: race condition si dos requests inicializan `GraphMemory()` en paralelo al startup
- Fix: agregar `_lock = threading.Lock()` a nivel de clase con doble check

**[ALTO]** `database/hardware_*.py:20` (4 archivos) — conexiones SQLite sin `PRAGMA journal_mode=WAL`
- Impacto: `SQLITE_BUSY` bajo carga concurrente (comparten `SQL_DB_PATH` con `sql_memory.py`)
- Fix: agregar `c.execute("PRAGMA journal_mode=WAL")` en cada `_conn()`

**[ALTO]** `memory/graph_memory.py:57` — escritura JSON directa sin rename atómico
- Impacto: crash durante escritura corrompe `graph_memory.json` irreversiblemente
- Fix:
  ```python
  tmp = path + ".tmp"
  with open(tmp, "w") as f: json.dump(data, f)
  os.replace(tmp, path)
  ```

**Duplicaciones confirmadas:**
- `memory/` (código) vs `memory_db/` (datos Qdrant) — sin duplicación, separación correcta
- `knowledge/` (código) vs `knowledge_feed/` (datos .txt) — sin duplicación, pero `knowledge_base.py` apunta a `agent_files/knowledge/`, no a `knowledge_feed/` — ruta de indexado desincronizada

---

### DOMINIO: AGENT (`agent/`, `llm/`, `tools/`)
> 5 ALTO / 7 MEDIO / 4 BAJO

**[ALTO]** `agent/orchestrator.py` — `CIRCUIT_DESIGN_KEYWORDS` lista literal ~80 strings sin tests de routing
- Impacto: typo en cualquier keyword rompe el clasificador silenciosamente
- Fix: extraer a `agent/keywords/circuit_keywords.py` con test unitario de cobertura

**[ALTO]** `agent/agent_controller.py:106` — `orchestrator.run()` sin `asyncio.wait_for()`
- Impacto: sub-agente colgado mantiene WebSocket abierto indefinidamente
- Fix: `await asyncio.wait_for(self.orchestrator.run(...), timeout=90.0)`

**[ALTO]** `agent/agent_controller.py:259-260` — `_store_episode` y `profiler.update_from_interaction` síncronos en path LLM general
- Impacto: bloqueo de ~300-800ms en la respuesta al usuario (otros paths usan `create_task`)
- Fix: `asyncio.create_task(asyncio.to_thread(_store_episode, ...))`

**[ALTO]** `llm/async_client.py:96-98` — `call_llm_text` captura toda `Exception` y retorna `""` sin retry
- Impacto: errores 429/timeout producen respuestas vacías silenciosas
- Fix: retry con backoff 1s para 429; re-raise para otros errores

**[ALTO]** `llm/cache.py:29-32` — `SemanticCache` muta `_entries` y `_exact` sin lock
- Impacto: race condition bajo concurrencia → cache corruption o KeyError
- Fix: agregar `threading.Lock()` en get/set

**[MEDIO]** `llm/async_client.py:116-141` — `stream_llm_async` sin timeout explícito en el stream
- Fix: `asyncio.wait_for(_client.stream(...), timeout=60.0)`

**[MEDIO]** `tools/schematic_renderer.py` vs `tools/pcb_renderer.py` — dispatch tables de tipos duplicadas y divergidas
- Fix: extraer a `tools/component_types.py` compartido

**Limpios:** `.mcp.json` (sin secrets), `agent_files/` (solo datos), `circuit_synthesizer.py` (integración OK post-v4.21)

---

### DOMINIO: INFRA (`Dockerfile`, `railway.toml`, configs)
> 3 ALTO / 5 MEDIO / 4 BAJO

**[ALTO]** `Dockerfile` — contenedor corre como `root` (sin `USER` declarado)
- Impacto: RCE = acceso root dentro del container
- Fix: agregar `RUN adduser --disabled-password appuser && USER appuser` antes del CMD

**[ALTO]** `Dockerfile:30` — `COPY . .` depende 100% de `.dockerignore` como barrera contra secrets
- Impacto: si `.dockerignore` falla, `.env` y `data/*.db` entran a la imagen
- Fix: auditar `.dockerignore` en CI o copiar selectivamente los directorios necesarios

**[ALTO]** `.env.example:34` — `JWT_SECRET` con placeholder de texto plano
- Impacto: si se usa sin cambiar → tokens JWT predecibles
- Fix: reemplazar por `JWT_SECRET=<generate: python -c "import secrets; print(secrets.token_hex(32))">`

**[MEDIO]** `Dockerfile:1` — imagen base sin digest/hash fijo
- Fix: `FROM python:3.11-slim@sha256:<hash>` o `python:3.11.9-slim`

**[MEDIO]** `Dockerfile:27` — `|| true` silencia fallo de descarga del modelo en build
- Fix: loguear el fallo o eliminar `|| true` para que el build falle (más seguro)

**[MEDIO]** `railway.toml` — `healthcheckTimeout=120` puede ser insuficiente si el modelo se descarga en runtime
- Fix: subir a `180` o asegurar que el modelo siempre se descargue en build

**[MEDIO]** `railway.toml` — `restartPolicyMaxRetries=3` deja la app caída permanentemente tras 3 crashes
- Fix: cambiar a `on_failure` sin límite de reintentos o subir a 10

**[BAJO]** `data/` no ignorado en `.gitignore` (`data/memory.db` existe en disco)
- Fix: agregar `data/*.db` al `.gitignore`

**[BAJO]** `.dockerignore` no ignora `data/` — 17KB de JSON dev + memory.db entran a la imagen
- Fix: agregar `data/` y `memory_db/` al `.dockerignore`

---

### DOMINIO: QA (`tests/`, `eval/`, configs de type)
> 7 ALTO / 8 MEDIO / 4 BAJO

**[ALTO]** `pytest.ini` — sin `testpaths` ni `--ignore=venv`
- Impacto: pytest recolecta miles de tests de numpy/sklearn del venv
- Fix: `testpaths = tests` + `addopts = --ignore=venv`

**[ALTO]** `eval/test_circuit_integration.py` y `eval/test_full_integration.py` — operan sobre DB de producción real
- Fix: usar fixture `tmp_db` de `tests/conftest.py`

**[ALTO]** README — "127/127 tests" son assertions individuales de `run_eval.py`, no funciones `def test_*` (son 56)
- Fix: actualizar README con conteo real y metodología

**[ALTO]** `eval/run_eval.py` tests 2, 9-11 — requieren Qdrant activo sin skip condicional
- Fix: `pytest.importorskip("qdrant_client")` + skip si `QDRANT_URL` no está configurada

**[ALTO]** `eval/test_e2e_api.py` — requiere servidor en `localhost:8000`; cuando pytest lo recolecta sin guard falla con `AttributeError`
- Fix: agregar `pytestmark = pytest.mark.skipif(not server_available(), reason="...")`

**[ALTO]** `tests/conftest.py` — `tmp_db` fixture sin `finally` para cleanup en fallo
- Fix: usar `yield` + `finally: os.unlink(tmp_path)` o `tmp_path` fixture de pytest

**[ALTO]** Módulos críticos sin ningún test: `agent/orchestrator.py`, `agent/agent_controller.py`, `llm/cache.py`, `tools/electrical_drc.py`, `tools/electrical_formulas.py` (25 fórmulas puras)
- Fix prioritario: `electrical_formulas.py` primero (0 deps, 25 fórmulas, ~30 tests triviales)

**¿Por qué dos type-checkers?** `pyrightconfig.json` fue generado automáticamente por VS Code/Pylance con `"pythonPlatform": "Windows"` — nunca fue decisión de arquitectura. Conflicto: mypy=Python 3.10, pyright=Python 3.11.
- Fix: agregar `pyrightconfig.json` al `.gitignore`; solo mypy en CI

---

### DOMINIO: MOBILE (`stratum-mobile/`)
> 3 ALTO / 4 MEDIO / 2 BAJO · Estado: ACTIVO, mantenimiento bajo

**[ALTO]** `stratum-mobile/android/app/google-services.json` — credenciales Firebase commiteadas
- Impacto: API keys de Firebase/Google expuestas en historial de git
- Fix:
  ```bash
  git rm --cached stratum-mobile/android/app/google-services.json
  echo "app/google-services.json" >> stratum-mobile/android/.gitignore
  ```
  Luego rotar las credenciales en Firebase Console

**[ALTO]** `stratum-mobile/android/.gitignore` — línea `# google-services.json` comentada deliberadamente
- Fix: descomentar → `google-services.json`

**[ALTO]** `stratum-mobile/` — sin `.gitignore` propio; `node_modules/` existe en disco y puede estar trackeado
- Fix: crear `stratum-mobile/.gitignore` con `node_modules/`, `android/.gradle/`, `android/app/build/`, `android/app/google-services.json`

**[MEDIO]** `capacitor.config.ts` — `cleartext: true` + `androidScheme: 'http'` innecesario (backend ya es HTTPS)
- Fix: eliminar `cleartext: true`, cambiar a `androidScheme: 'https'`

**[MEDIO]** `stratum-mobile/package.json` — `"typescript": "^6.0.2"` (TypeScript 6 no existe → `npm install` falla)
- Fix: `"typescript": "^5.4.0"`

**[MEDIO]** `android/app/build.gradle` — `minifyEnabled false` en release build
- Fix: `minifyEnabled true` + `proguardFiles getDefaultProguardFile('proguard-android-optimize.txt')`

**[MEDIO]** `www/index.html` — `DEFAULT_BACKEND` hardcodeado en JS
- Fix: leer desde `capacitor.config.ts` server.url o variable de build

---

## PARTE 3 — TRANSVERSALES

### Seguridad

**[ALTO]** `core/config.py:134` — `JWT_SECRET = _env("JWT_SECRET", "stratum-dev-secret-change-in-production")`
- Impacto: tokens JWT forgeables si la env var no está configurada en Railway
- Fix:
  ```python
  JWT_SECRET = _env("JWT_SECRET", "")
  # en validate_config():
  if MULTI_USER and not JWT_SECRET:
      raise ValueError("JWT_SECRET requerido cuando MULTI_USER=true")
  ```

**[ALTO]** `.env` existe en disco pero no está en `.gitignore` explícitamente
- Fix: agregar línea `.env` al `.gitignore` (sin wildcard, explícita)

**[ALTO]** `database/intelligence.py:206` — f-string en UPDATE con campos dinámicos
- Fix: whitelist de columnas antes de construir el query

**[MEDIO]** `database/component_stock.py:91`, `database/sql_memory.py:383` — f-strings en queries UPDATE
- Fix: whitelist de columnas permitidas en ambos sitios

### Dependencias

**[ALTO]** `stratum-mobile/package.json` — `"typescript": "^6.0.2"` (no existe → `npm install` roto)
- Fix: `"typescript": "^5.4.0"`

**[MEDIO]** `requirements.txt` — `pytest>=8.0.0` y `pytest-asyncio>=0.23.0` en deps de producción
- Fix: mover a `requirements-dev.txt`; Dockerfile solo instala `requirements.txt`

**[MEDIO]** `requirements.txt` — `numpy>=1.24.0` sin upper bound (NumPy 2.x tiene breaking changes)
- Fix: `numpy>=1.24.0,<2.0.0`

**[MEDIO]** `package.json` raíz — `@aethermind/*` (4 packages sin uso en ningún archivo del proyecto)
- Fix: eliminar `package.json` y `package-lock.json` raíz

### Tests (cross-cutting)

**[ALTO]** `pytest.ini` sin `testpaths` → recolecta tests de `venv/`
- Fix: `testpaths = tests`

**[ALTO]** Tests de `eval/` contaminan DB de producción
- Fix: usar `tmp_db` fixture

### Config IDE

**[MEDIO]** `.cursorrules` y `.windsurfrules` son idénticos — mantenimiento duplicado
- Fix: eliminar `.windsurfrules`

**[MEDIO]** `pyrightconfig.json`, `.cursor/`, `.kiro/`, `.opencode.json` no están en `.gitignore`
- Fix: agregar todos a `.gitignore`

### Archivos sospechosos

**[MEDIO]** `guide-test.py` en raíz — propósito no claro, puede confundir a pytest
- Fix: mover a `tests/` o eliminar

**[BAJO]** `instruc.txt` — canal de comunicación temporal, no es código
- Fix: agregar a `.gitignore`

**[BAJO]** `package-lock.json` raíz — lockfile huérfano (su `package.json` tiene deps sin uso)
- Fix: eliminar junto con `package.json` raíz
