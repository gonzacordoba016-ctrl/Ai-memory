from agent.keywords.circuit_keywords import (
    CIRCUIT_DESIGN_KEYWORDS,
    HARDWARE_KEYWORDS,
    MEMORY_KEYWORDS,
)


def test_no_duplicates_within_circuit_keywords():
    seen = set()
    dupes = []
    for kw in CIRCUIT_DESIGN_KEYWORDS:
        if kw in seen:
            dupes.append(kw)
        seen.add(kw)
    assert not dupes, f"Duplicados en CIRCUIT_DESIGN_KEYWORDS: {dupes}"


def test_no_duplicates_within_hardware_keywords():
    seen = set()
    dupes = []
    for kw in HARDWARE_KEYWORDS:
        if kw in seen:
            dupes.append(kw)
        seen.add(kw)
    assert not dupes, f"Duplicados en HARDWARE_KEYWORDS: {dupes}"


def test_no_duplicates_within_memory_keywords():
    seen = set()
    dupes = []
    for kw in MEMORY_KEYWORDS:
        if kw in seen:
            dupes.append(kw)
        seen.add(kw)
    assert not dupes, f"Duplicados en MEMORY_KEYWORDS: {dupes}"


def test_no_overlap_between_lists():
    cd = set(CIRCUIT_DESIGN_KEYWORDS)
    hw = set(HARDWARE_KEYWORDS)
    mem = set(MEMORY_KEYWORDS)

    cd_hw = cd & hw
    assert not cd_hw, f"Overlap CIRCUIT_DESIGN ∩ HARDWARE: {sorted(cd_hw)}"

    cd_mem = cd & mem
    assert not cd_mem, f"Overlap CIRCUIT_DESIGN ∩ MEMORY: {sorted(cd_mem)}"

    hw_mem = hw & mem
    assert not hw_mem, f"Overlap HARDWARE ∩ MEMORY: {sorted(hw_mem)}"
