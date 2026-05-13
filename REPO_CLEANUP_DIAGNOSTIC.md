# Diagnostico previo de limpieza del repositorio

Fecha: 2026-05-12

Estado: solo lectura. No se borro ni modifico nada durante este diagnostico.

## Resumen

El repositorio tiene mucho peso recuperable en artefactos locales:

| Categoria | Tamano aproximado | Accion |
|---|---:|---|
| `venv/` | 983.91 MB | Borrar seguro; se recrea con `pip install -r requirements.txt` |
| `.code-review-graph/` | 540.22 MB | Borrar seguro |
| `__pycache__/` | 163.45 MB | Borrar seguro |
| `stratum-mobile/` completo | 81.68 MB | Requiere decision |
| `stratum-mobile/node_modules/` | 40.27 MB | Borrar seguro si se mantiene mobile |
| `stratum-mobile/android/app/build/` | 37.65 MB | Borrar seguro |
| `node_modules/` | 6.32 MB | Borrar seguro |
| `memory_db/` | 1.95 MB | No borrar sin backup remoto |

## 1. Archivos grandes no core

| Ruta | Tamano | Accion sugerida |
|---|---:|---|
| `.code-review-graph/graph.db` | 540.2 MB | Borrar seguro |
| `venv/` | 983.9 MB | Borrar seguro; se recrea |
| `node_modules/` | 6.3 MB | Borrar seguro |
| `stratum-mobile/node_modules/` | 40.3 MB | Borrar seguro si se mantiene mobile |
| `stratum-mobile/android/app/build/` | 37.7 MB | Borrar seguro |
| `stratum-mobile/android/.gradle/` | 3.2 MB | Borrar seguro |
| `memory_db/collection/agent_memory/storage.sqlite` | 2.0 MB | No borrar sin backup remoto |
| `database/memory.db-wal` | 305.8 KB | No borrar; DB local core |
| `database/memory.db` | 260.0 KB | No borrar; DB local core |
| `imagen/c.PNG` | 371.2 KB | No borrar sin revisar uso |
| `imagen/b.PNG` | 176.1 KB | No borrar sin revisar uso |
| `imagen/d.PNG` | 164.5 KB | No borrar sin revisar uso |
| `imagen/a.PNG` | 55.6 KB | No borrar sin revisar uso |
| `.aider.tags.cache.v4/cache.db` | 152.0 KB | Borrar seguro |
| `CONTEXT-PROJECT.md` | 137.4 KB | Borrar; reemplazado por `STRATUM.md` |
| `logs/local-server.err.log` | 53.1 KB | Borrar seguro |

## 2. Directorios que se pueden borrar sin impacto

| Directorio | Existe | Tamano | Items | Estado |
|---|---:|---:|---:|---|
| `node_modules/` | si | 6.32 MB | 1510 | Seguro |
| `venv/` | si | 983.91 MB | 33022 | Seguro |
| `.pytest_cache/` | si | 0.03 MB | 6 | Seguro |
| `.aider.tags.cache.v4/` | si | 0.18 MB | 3 | Seguro |
| `stratum-mobile/node_modules/` | si | 40.27 MB | 2451 | Seguro si se mantiene mobile |
| `stratum-mobile/android/app/build/` | si | 37.65 MB | 576 | Seguro |
| `stratum-mobile/android/.gradle/` | si | 3.17 MB | 18 | Seguro |
| `memory_db/` | si | 1.95 MB | 3 | Pendiente backup remoto |
| `.code-review-graph/` | si | 540.22 MB | 2 | Seguro |
| `logs/` | si | 0.08 MB | 2 | Seguro |
| `.cursor/` | si | 0 MB | 1 | Seguro |
| `.kiro/` | si | 0 MB | 2 | Seguro |

### `__pycache__/`

| Alcance | Cantidad | Tamano |
|---|---:|---:|
| Todos los `__pycache__/` | 1140 dirs | 163.45 MB |
| Fuera de `venv/` | 21 dirs | 2.63 MB |

Top `__pycache__/` fuera de `venv/`:

| Ruta | Tamano | Items |
|---|---:|---:|
| `tests/__pycache__/` | 680.4 KB | 26 |
| `tools/__pycache__/` | 487.8 KB | 43 |
| `tools/eda/__pycache__/` | 379.4 KB | 12 |
| `api/routers/__pycache__/` | 254.6 KB | 32 |
| `agent/agents/__pycache__/` | 198.5 KB | 14 |
| `database/__pycache__/` | 149.1 KB | 11 |
| `agent/__pycache__/` | 141.7 KB | 17 |
| `eval/__pycache__/` | 111.8 KB | 9 |
| `memory/__pycache__/` | 57.7 KB | 11 |
| `api/__pycache__/` | 30.4 KB | 8 |

## 3. Archivos de IDE/tooling no necesarios

| Ruta | Existe | Tamano | Tracked | Accion |
|---|---:|---:|---:|---|
| `.cursor/` | si | 0 MB | no | Borrar |
| `.kiro/` | si | 0 MB | no | Borrar |
| `.opencode.json` | si | 0.2 KB | no | Borrar |
| `.cursorrules` | si | 1.8 KB | no | Borrar |
| `.windsurfrules` | no | - | - | Nada |
| `.aider.tags.cache.v4/` | si | 0.18 MB | no | Borrar |

## 4. Archivos de Railway que ya no se necesitan

| Archivo | Existe | Tamano | Tracked | Accion |
|---|---:|---:|---:|---|
| `railway.toml` | si | 0.2 KB | si | Borrar si el proyecto queda solo local |
| `Dockerfile` | si | 1.7 KB | si | Borrar si no hay deploy Docker |
| `.dockerignore` | si | 0.7 KB | si | Borrar si no hay Docker |

## 5. Documentos historicos reemplazados por `STRATUM.md`

| Archivo | Existe | Tamano | Tracked | Accion |
|---|---:|---:|---:|---|
| `CONTEXT-PROJECT.md` | si | 137.4 KB | si | Borrar |
| `AUDIT.md` | no, ya aparece borrado en working tree | - | si | Confirmar baja |
| `AUDITORIA.md` | si | 17.9 KB | no | Borrar |
| `docs/PRE_CLEANUP_AUDIT.md` | si | 21.2 KB | no | Mantener en `docs/` como referencia |
| `docs/ARCHITECTURE.md` | no evaluado para borrar | - | - | Mantener |

## 6. Archivos de `eval/` que no corren en CI

| Archivo | Existe | Tamano | Tracked | Accion |
|---|---:|---:|---:|---|
| `eval/run_eval.py` | si | 48.5 KB | si | Borrar |
| `eval/test_e2e_api.py` | si | 13.5 KB | si | Borrar |
| `eval/test_full_integration.py` | si | 11.6 KB | si | Borrar |

Otros archivos `eval/` trackeados encontrados:

| Archivo | Accion |
|---|---|
| `eval/__init__.py` | Mantener salvo decision contraria |
| `eval/conftest.py` | Mantener salvo decision contraria |
| `eval/test_circuit_integration.py` | Mantener salvo decision contraria |

## 7. Estado de `.gitignore`

Ya incluye:

```gitignore
__pycache__/
*.py[cod]
.pytest_cache/
venv/
.env
memory_db/
.aider*
.cursor/
.kiro/
.opencode.json
.cursorrules
node_modules/
logs/
instruc.txt
.code-review-graph/
stratum-mobile/
```

Faltan o conviene agregar de forma explicita:

```gitignore
*.pyc
data/
*.db
stratum-mobile/node_modules/
stratum-mobile/android/app/build/
```

Nota: `.gitignore` ya ignora `data/*.db`, pero el pedido especifica `data/`.

## 8. Archivos trackeados relevantes

El barrido de `git ls-files` encontro estos candidatos trackeados:

```text
.dockerignore
AUDIT.md
CONTEXT-PROJECT.md
Dockerfile
eval/__init__.py
eval/conftest.py
eval/run_eval.py
eval/test_circuit_integration.py
eval/test_e2e_api.py
eval/test_full_integration.py
railway.toml
stratum-mobile/android/app/build.gradle
```

`stratum-mobile/` tiene 57 archivos trackeados. Tambien hay cambios locales previos en:

```text
stratum-mobile/capacitor.config.ts
stratum-mobile/package.json
```

## 9. Decisiones necesarias antes de borrar

| Item | Decision |
|---|---|
| `memory_db/` | No borrar hasta confirmar backup remoto o aceptar perdida del Qdrant local |
| `stratum-mobile/` | Confirmar si se mantiene como subproyecto o se elimina completo |

## 10. Limpieza segura propuesta sin decisiones pendientes

Seguro para borrar sin tocar funcionalidad core:

```text
node_modules/
venv/
__pycache__/ en todas partes
.pytest_cache/
.aider.tags.cache.v4/
.code-review-graph/
logs/
.cursor/
.kiro/
.opencode.json
.cursorrules
railway.toml
Dockerfile
.dockerignore
CONTEXT-PROJECT.md
AUDITORIA.md
AUDIT.md
eval/run_eval.py
eval/test_e2e_api.py
eval/test_full_integration.py
```

Mantener por ahora:

```text
memory_db/
database/memory.db*
docs/PRE_CLEANUP_AUDIT.md
docs/ARCHITECTURE.md
stratum-mobile/
```

Si se decide mantener `stratum-mobile/`, borrar solo:

```text
stratum-mobile/node_modules/
stratum-mobile/android/app/build/
stratum-mobile/android/.gradle/
```

Si se decide eliminar `stratum-mobile/`, borrar completo:

```text
stratum-mobile/
```
