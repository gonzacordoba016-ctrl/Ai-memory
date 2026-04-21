# tests/test_versioning_sharing.py
import pytest


class TestVersioning:
    def test_save_version_returns_version_number(self, mgr, sample_circuit):
        design_id = mgr.save_design(sample_circuit)
        ver = mgr.save_version(design_id, reason="test")
        assert ver == 1

    def test_second_version_increments(self, mgr, sample_circuit):
        design_id = mgr.save_design(sample_circuit)
        mgr.save_version(design_id, reason="v1")
        ver2 = mgr.save_version(design_id, reason="v2")
        assert ver2 == 2

    def test_save_version_unknown_circuit(self, mgr):
        ver = mgr.save_version(99999, reason="ghost")
        assert ver == -1

    def test_get_versions_returns_list(self, mgr, sample_circuit):
        design_id = mgr.save_design(sample_circuit)
        mgr.save_version(design_id, reason="initial")
        versions = mgr.get_versions(design_id)
        assert isinstance(versions, list)
        assert len(versions) >= 1

    def test_version_has_required_fields(self, mgr, sample_circuit):
        design_id = mgr.save_design(sample_circuit)
        mgr.save_version(design_id, reason="check fields")
        versions = mgr.get_versions(design_id)
        v = versions[0]
        assert "version" in v
        assert "reason" in v
        assert "created_at" in v
        assert "components" in v
        assert "nets" in v

    def test_version_reason_stored(self, mgr, sample_circuit):
        design_id = mgr.save_design(sample_circuit)
        mgr.save_version(design_id, reason="my reason")
        versions = mgr.get_versions(design_id)
        assert versions[0]["reason"] == "my reason"

    def test_get_version_snapshot(self, mgr, sample_circuit):
        design_id = mgr.save_design(sample_circuit)
        mgr.save_version(design_id, reason="snap")
        snap = mgr.get_version_snapshot(design_id, 1)
        assert snap is not None
        assert snap["name"] == sample_circuit["name"]
        assert len(snap["components"]) == len(sample_circuit["components"])

    def test_get_version_snapshot_not_found(self, mgr, sample_circuit):
        design_id = mgr.save_design(sample_circuit)
        snap = mgr.get_version_snapshot(design_id, 999)
        assert snap is None

    def test_restore_to_version(self, mgr, sample_circuit):
        design_id = mgr.save_design(sample_circuit)
        mgr.save_version(design_id, reason="original")

        # Modify circuit: remove a component
        mgr.update_circuit(design_id, [sample_circuit["components"][0]], sample_circuit["nets"])

        # Restore to version 1
        ok = mgr.restore_to_version(design_id, 1)
        assert ok is True

        restored = mgr.get_design(design_id)
        assert len(restored["components"]) == len(sample_circuit["components"])

    def test_restore_auto_saves_current(self, mgr, sample_circuit):
        design_id = mgr.save_design(sample_circuit)
        mgr.save_version(design_id, reason="v1")
        mgr.restore_to_version(design_id, 1)
        # Should now have v1 + auto-save before restore = 2 versions
        versions = mgr.get_versions(design_id)
        assert len(versions) >= 2

    def test_diff_shows_added_components(self, mgr, sample_circuit):
        design_id = mgr.save_design(sample_circuit)
        mgr.save_version(design_id, reason="before add")
        # Add component
        new_comps = sample_circuit["components"] + [
            {"id": "C1", "name": "Cap 100nF", "type": "capacitor", "value": "100", "unit": "nF"}
        ]
        mgr.update_circuit(design_id, new_comps, sample_circuit["nets"])
        mgr.save_version(design_id, reason="after add")
        versions = mgr.get_versions(design_id)
        last = versions[0]
        assert "C1" in last["diff"].get("added", [])


class TestSharing:
    def test_create_share_returns_token(self, mgr, sample_circuit):
        design_id = mgr.save_design(sample_circuit)
        token = mgr.create_share(design_id)
        assert isinstance(token, str)
        assert len(token) > 8

    def test_create_share_idempotent(self, mgr, sample_circuit):
        design_id = mgr.save_design(sample_circuit)
        token1 = mgr.create_share(design_id)
        token2 = mgr.create_share(design_id)
        assert token1 == token2

    def test_get_by_share_token(self, mgr, sample_circuit):
        design_id = mgr.save_design(sample_circuit)
        token = mgr.create_share(design_id)
        data = mgr.get_by_share_token(token)
        assert data is not None
        assert data["name"] == sample_circuit["name"]

    def test_get_by_invalid_token(self, mgr):
        data = mgr.get_by_share_token("definitely-not-valid-abc123")
        assert data is None

    def test_revoke_share(self, mgr, sample_circuit):
        design_id = mgr.save_design(sample_circuit)
        token = mgr.create_share(design_id)
        mgr.revoke_share(design_id)
        data = mgr.get_by_share_token(token)
        assert data is None

    def test_revoke_then_create_new_token(self, mgr, sample_circuit):
        design_id = mgr.save_design(sample_circuit)
        token1 = mgr.create_share(design_id)
        mgr.revoke_share(design_id)
        token2 = mgr.create_share(design_id)
        # New token is different from revoked one
        assert token1 != token2


class TestUpdateCircuit:
    def test_update_components(self, mgr, sample_circuit):
        design_id = mgr.save_design(sample_circuit)
        new_comps = [{"id": "U1", "name": "ESP32", "type": "esp32", "value": "", "unit": ""}]
        ok = mgr.update_circuit(design_id, new_comps, sample_circuit["nets"])
        assert ok is True
        updated = mgr.get_design(design_id)
        assert len(updated["components"]) == 1
        assert updated["components"][0]["id"] == "U1"
        assert updated["components"][0]["type"] == "esp32"

    def test_update_name(self, mgr, sample_circuit):
        design_id = mgr.save_design(sample_circuit)
        mgr.update_circuit(design_id, sample_circuit["components"], sample_circuit["nets"], name="Nuevo Nombre")
        updated = mgr.get_design(design_id)
        assert updated["name"] == "Nuevo Nombre"

    def test_update_nonexistent_circuit(self, mgr, sample_circuit):
        ok = mgr.update_circuit(99999, sample_circuit["components"], sample_circuit["nets"])
        assert ok is False

    def test_update_owner(self, mgr, sample_circuit):
        design_id = mgr.save_design(sample_circuit, user_id="user_a")
        ok = mgr.update_owner(design_id, "user_b")
        assert ok is True
        # Verify by listing: user_a should no longer see it, user_b should
        user_a_designs = mgr.list_designs("user_a")
        user_b_designs = mgr.list_designs("user_b")
        assert not any(d["id"] == design_id for d in user_a_designs)
        assert any(d["id"] == design_id for d in user_b_designs)
