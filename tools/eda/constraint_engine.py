"""
Constraint Engine — DRC declarativo sobre Circuit IR.

Reemplaza:
    - tools/electrical_drc.py        (18 checks hardcoded)
    - tools/mcu_pinout_validator.py  (validate_pinout)

Cada regla es una función (`RuleFn`) registrada via decorator. La engine
recorre todas las reglas habilitadas, recolecta `ValidationIssue` y los
clasifica por severidad.

API pública:
    run_drc(circuit)       → dict {issues, errors, warnings, info, summary}
    validate(circuit)      → list[ValidationIssue]
    rule_registry          → singleton del registry de reglas
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Iterator

from tools.eda.component_registry import ComponentSpec, get_registry
from tools.eda.ir import (
    Circuit,
    Component,
    Net,
    Severity,
    ValidationIssue,
)


# ────────────────────────────────────────────────────────────────────────────
# Validation Context — datos pre-computados para las reglas
# ────────────────────────────────────────────────────────────────────────────


@dataclass
class ValidationContext:
    """Snapshot indexado del circuito para que las reglas sean O(1)."""

    circuit: Circuit
    # ref → Component
    comp_by_ref: dict[str, Component] = field(default_factory=dict)
    # ref → ComponentSpec del registry (None si no encontrado)
    spec_by_ref: dict[str, ComponentSpec | None] = field(default_factory=dict)
    # net_name → set[component_ref]
    refs_in_net: dict[str, set[str]] = field(default_factory=dict)
    # ref → set[net_name]  (todos los nets a los que pertenece el componente)
    nets_of_ref: dict[str, set[str]] = field(default_factory=dict)
    # category → set[ref]
    refs_by_category: dict[str, set[str]] = field(default_factory=dict)

    @classmethod
    def build(cls, circuit: Circuit) -> "ValidationContext":
        ctx = cls(circuit=circuit)
        registry = get_registry()
        for c in circuit.components:
            ctx.comp_by_ref[c.ref] = c
            spec = registry.get(c.type)
            ctx.spec_by_ref[c.ref] = spec
            cat = spec.category if spec else "unknown"
            ctx.refs_by_category.setdefault(cat, set()).add(c.ref)
        for net in circuit.nets:
            refs = {node.ref for node in net.nodes}
            ctx.refs_in_net[net.name] = refs
            for r in refs:
                ctx.nets_of_ref.setdefault(r, set()).add(net.name)
        return ctx

    # ── Helpers ──────────────────────────────────────────────────────────────

    def category_of(self, ref: str) -> str:
        return (self.spec_by_ref.get(ref).category
                if self.spec_by_ref.get(ref) else "unknown")

    def refs_of_category(self, *categories: str) -> set[str]:
        out: set[str] = set()
        for c in categories:
            out |= self.refs_by_category.get(c, set())
        return out

    def refs_of_types(self, *types: str) -> set[str]:
        types_l = {t.lower() for t in types}
        return {ref for ref, c in self.comp_by_ref.items()
                if c.type.lower() in types_l}

    def has_net_named(self, *substrings: str) -> bool:
        return any(self._matches(n.name, substrings) for n in self.circuit.nets)

    def nets_named(self, *substrings: str) -> list[Net]:
        return [n for n in self.circuit.nets
                if self._matches(n.name, substrings)]

    @staticmethod
    def _matches(name: str, substrings: tuple[str, ...]) -> bool:
        nl = name.lower()
        return any(s in nl for s in substrings)

    @staticmethod
    def is_vcc_net(name: str) -> bool:
        n = name.lower()
        return any(k in n for k in ("vcc", "5v", "3v3", "3.3v", "vin", "vdd",
                                    "+5v", "+3.3v", "12v", "+12v"))

    @staticmethod
    def is_gnd_net(name: str) -> bool:
        n = name.lower()
        return any(k in n for k in ("gnd", "ground", "agnd", "dgnd", "pgnd"))


# ────────────────────────────────────────────────────────────────────────────
# Rule abstraction
# ────────────────────────────────────────────────────────────────────────────


RuleFn = Callable[[ValidationContext], Iterator[ValidationIssue]]


@dataclass
class ConstraintRule:
    name: str
    description: str
    fn: RuleFn
    enabled: bool = True
    tags: tuple[str, ...] = ()


class RuleRegistry:
    def __init__(self) -> None:
        self._rules: dict[str, ConstraintRule] = {}

    def register(
        self,
        name: str,
        *,
        description: str = "",
        tags: Iterable[str] = (),
    ) -> Callable[[RuleFn], RuleFn]:
        def decorator(fn: RuleFn) -> RuleFn:
            if name in self._rules:
                raise ValueError(f"Regla duplicada: {name}")
            self._rules[name] = ConstraintRule(
                name=name,
                description=description or fn.__doc__ or "",
                fn=fn,
                tags=tuple(tags),
            )
            return fn
        return decorator

    def all(self) -> list[ConstraintRule]:
        return list(self._rules.values())

    def get(self, name: str) -> ConstraintRule | None:
        return self._rules.get(name)

    def disable(self, name: str) -> None:
        if name in self._rules:
            self._rules[name].enabled = False

    def enable(self, name: str) -> None:
        if name in self._rules:
            self._rules[name].enabled = True


rule_registry = RuleRegistry()


# ────────────────────────────────────────────────────────────────────────────
# Engine
# ────────────────────────────────────────────────────────────────────────────


def validate(
    circuit: Circuit,
    *,
    rules: Iterable[str] | None = None,
) -> list[ValidationIssue]:
    """Corre las reglas habilitadas sobre el circuito.

    Args:
        circuit: Circuit IR a validar.
        rules: si se pasa, solo corre estas reglas por nombre.
               Si None, corre todas las habilitadas.
    """
    # Importar reglas concretas (registra los decoradores).
    from tools.eda import rules as _rules  # noqa: F401

    ctx = ValidationContext.build(circuit)
    selected: list[ConstraintRule]
    if rules is None:
        selected = [r for r in rule_registry.all() if r.enabled]
    else:
        names = set(rules)
        selected = [r for r in rule_registry.all() if r.name in names]

    issues: list[ValidationIssue] = []
    for rule in selected:
        try:
            for issue in rule.fn(ctx):
                # Sello la regla origen si la regla no lo hizo.
                if issue.rule is None:
                    issue = issue.model_copy(update={"rule": rule.name})
                issues.append(issue)
        except Exception as e:
            issues.append(ValidationIssue(
                code="RULE_INTERNAL_ERROR",
                severity=Severity.WARNING,
                message=f"Regla '{rule.name}' falló internamente: {e}",
                rule=rule.name,
            ))
    return issues


def run_drc(circuit: Circuit) -> dict:
    """API compatible con `tools.electrical_drc.run_drc` (devuelve dicts)."""
    issues = validate(circuit)
    errors = [i for i in issues if i.severity == Severity.ERROR]
    warnings = [i for i in issues if i.severity == Severity.WARNING]
    info = [i for i in issues if i.severity == Severity.INFO]

    if not errors and not warnings:
        summary = "DRC OK — sin issues."
    else:
        bits = []
        if errors:
            bits.append(f"{len(errors)} error{'es' if len(errors) != 1 else ''}")
        if warnings:
            bits.append(f"{len(warnings)} warning{'s' if len(warnings) != 1 else ''}")
        summary = "DRC: " + ", ".join(bits) + "."

    return {
        "issues":   [i.model_dump(exclude_none=True) for i in issues],
        "errors":   [i.model_dump(exclude_none=True) for i in errors],
        "warnings": [i.model_dump(exclude_none=True) for i in warnings],
        "info":     [i.model_dump(exclude_none=True) for i in info],
        "summary":  summary,
    }
