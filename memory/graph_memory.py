# memory/graph_memory.py

import json
import re
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path

import networkx as nx

from core.config import GRAPH_DB_PATH
from core.logger import logger


class GraphMemory:

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.graph = nx.DiGraph()
        self._seq  = 0
        self._load()
        self._initialized = True

    def _load(self):
        path = Path(GRAPH_DB_PATH)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                try:
                    # NetworkX 3.2+ acepta el kwarg edges= para especificar la clave
                    # Aseguramos que el dict use "edges" (renombrando "links" si es necesario)
                    data_new = dict(data)
                    if "links" in data_new and "edges" not in data_new:
                        data_new["edges"] = data_new.pop("links")
                    self.graph = nx.node_link_graph(data_new, edges="edges")
                except TypeError:
                    # NetworkX < 3.2: no acepta edges=, espera la clave "links"
                    data_old = dict(data)
                    if "edges" in data_old and "links" not in data_old:
                        data_old["links"] = data_old.pop("edges")
                    self.graph = nx.node_link_graph(data_old)
                logger.info(f"Grafo cargado: {self.graph.number_of_nodes()} nodos, "
                            f"{self.graph.number_of_edges()} aristas")
            except Exception as e:
                logger.error(f"Error cargando grafo: {e}")
                self.graph = nx.DiGraph()

    def save(self):
        path = Path(GRAPH_DB_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = nx.node_link_data(self.graph)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_relation(self, subject: str, predicate: str, obj: str, source: str = "conversation"):
        subject = subject.strip().lower()
        obj     = obj.strip().lower()

        for node in (subject, obj):
            if node not in self.graph:
                self.graph.add_node(node, created_at=datetime.now(timezone.utc).isoformat())

        self.graph.add_edge(
            subject, obj,
            predicate  = predicate.strip().lower(),
            source     = source,
            updated_at = datetime.now(timezone.utc).isoformat(),
        )
        self.save()
        self._seq += 1
        logger.info(f"Grafo: [{subject}] --{predicate}--> [{obj}]")

    def add_facts_from_dict(self, facts: dict, user_label: str = "usuario"):
        mapping = {
            "user_name":      ("se_llama",     lambda v: v),
            "user_job":       ("trabaja_como", lambda v: v),
            "user_company":   ("trabaja_en",   lambda v: v),
            "user_location":  ("vive_en",      lambda v: v),
            "user_interests": ("le_interesa",  lambda v: v),
            "partner_name":   ("pareja_es",    lambda v: v),
            "user_age":       ("tiene_edad",   lambda v: f"{v} años"),
        }
        for key, value in facts.items():
            if key in mapping and value:
                predicate, transform = mapping[key]
                self.add_relation(user_label, predicate, transform(value), source="sql_facts")

    def get_related(self, entity: str, depth: int = 2) -> list[str]:
        entity = entity.strip().lower()
        if entity not in self.graph:
            return []

        results = []
        visited = set()

        def traverse(node, current_depth):
            if current_depth > depth or node in visited:
                return
            visited.add(node)
            for _, neighbor, data in self.graph.out_edges(node, data=True):
                predicate = data.get("predicate", "relacionado_con")
                results.append(f"{node} {predicate} {neighbor}")
                traverse(neighbor, current_depth + 1)

        traverse(entity, 0)
        return results

    def get_context_for_query(self, query: str) -> str:
        entities      = self._extract_entities(query)
        all_relations = []

        for entity in entities:
            relations = self.get_related(entity, depth=2)
            all_relations.extend(relations)

        if not all_relations:
            all_relations = self.get_related("usuario", depth=2)

        if not all_relations:
            return ""

        deduped = list(dict.fromkeys(all_relations))
        unique  = list(islice(deduped, 10))
        lines   = "\n".join(f"- {r}" for r in unique)
        return f"Relaciones conocidas:\n{lines}"

    def get_all_relations(self) -> list[dict]:
        results = []
        for src, dst, data in self.graph.edges(data=True):
            results.append({
                "subject":   src,
                "predicate": data.get("predicate", ""),
                "object":    dst,
                "source":    data.get("source", ""),
            })
        return results

    def stats(self) -> dict:
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
        }

    def _extract_entities(self, text: str) -> list[str]:
        known      = list(self.graph.nodes())
        found      = []
        text_lower = text.lower()

        for node in known:
            if node in text_lower:
                found.append(node)

        capitalized = re.findall(r'\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}\b', text)
        found.extend([w.lower() for w in capitalized])

        return list(set(found))


graph_memory = GraphMemory()