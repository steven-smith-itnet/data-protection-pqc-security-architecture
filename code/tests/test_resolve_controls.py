import json
import os
import re

import pytest

import resolve_controls as rc

CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POLICY = rc.load_policy()


def resolve(*pairs, **kw):
    return rc.resolve(rc.parse_tags(list(pairs)), POLICY, **kw)


def errors(*pairs):
    return rc.validate_tags(rc.parse_tags(list(pairs)), POLICY)[0]


def test_restricted_payment_resolves_to_pp3_pci():
    r = resolve("data-classification=restricted", "data-domain=payment", "regulatory-scope=pci_gdpr")
    assert (r["tier"], r["label"], r["protection_profile"]) == ("C3", "Restricted\\PCI", "pp3")
    assert r["data_states"]["at_rest"]["dlp_action"] == "block"
    assert any("3.5.1.1" in c for c in r["overlays"]["regulatory-scope:pci"])
    assert "regulatory-scope:gdpr" in r["overlays"]
    assert set(r["clouds"]) == {"aws", "azure", "gcp", "oci", "on_prem"}


def test_confidential_guest_is_pp2():
    r = resolve("data-classification=confidential", "data-domain=guest", "regulatory-scope=gdpr", cloud="azure")
    assert r["protection_profile"] == "pp2"
    assert r["label"] == "Confidential\\Guest-PII"
    assert list(r["clouds"]) == ["azure"]
    assert r["common"]["key_admin_user_separation"] is True


def test_pp3_inherits_from_pp2():
    merged = rc.profile_controls("pp3", POLICY)
    assert "inherits" not in merged
    assert merged["data_states"]["in_transit"]["mtls"] == "required for service-to-service"


def test_higher_profile_allowed_with_warning():
    r = resolve("data-classification=internal", "protection-profile=pp2")
    assert r["protection_profile"] == "pp2"
    assert any("exceeds" in w for w in r["warnings"])


def test_retention_overlay():
    r = resolve("data-classification=confidential", "retention-class=legal-hold")
    assert "retention-class:legal-hold" in r["overlays"]


@pytest.mark.parametrize("pairs,fragment", [
    (["data-classification=secret"], "not allowed"),
    (["data-classification=confidential", "protection-profile=pp1"], "weaker"),
    (["data-classification=confidential", "regulatory-scope=pci"], "requires data-classification='restricted'"),
    (["data-classification=restricted", "regulatory-scope=none_gdpr"], "cannot be combined"),
    (["data-classification=restricted", "regulatory-scope=gdpr_hipaa"], "unknown value"),
    (["data-classification=restricted", "regulatory-scope=gdpr_gdpr"], "duplicate"),
    (["data-classification=Restricted"], "lowercase"),
    (["data-domain=guest"], "required tag 'data-classification' is missing"),
    (["data-classification=internal", "data-owner=Guest Platform"], "lowercase"),
])
def test_validation_errors(pairs, fragment):
    errs = errors(*pairs)
    assert any(fragment in e for e in errs), errs


def test_label_override_must_match_tier():
    with pytest.raises(rc.TagValidationError):
        resolve("data-classification=confidential", label="Restricted\\PCI")
    r = resolve("data-classification=restricted", label="Restricted\\Special-Category")
    assert r["label"] == "Restricted\\Special-Category"


def test_cli_exit_codes(capsys):
    assert rc.main(["data-classification=restricted", "data-domain=payment", "regulatory-scope=pci", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["protection_profile"] == "pp3"
    assert rc.main(["data-classification=nope"]) == 1


# ---- cross-artifact consistency: YAML schema == Terraform validation == OPA ----

def _tf_list(text, var):
    m = re.search(r'contains\(\s*\[([^\]]*)\],\s*d\.' + var, text)
    assert m, var
    return re.findall(r'"([^"]+)"', m.group(1))


@pytest.mark.parametrize("cloud", ["aws", "azure", "gcp", "oci"])
def test_terraform_validation_matches_policy_schema(cloud):
    text = open(os.path.join(CODE_DIR, "terraform", cloud, "tag_variables.tf")).read()
    keys = POLICY["schema"]["keys"]
    assert _tf_list(text, "data_domain") == keys["data-domain"]
    assert _tf_list(text, "data_classification") == keys["data-classification"]
    assert _tf_list(text, "data_residency") == keys["data-residency"]
    assert _tf_list(text, "retention_class") == keys["retention-class"]
    atoms = [a for a in keys["regulatory-scope-atoms"] if a != "none"]
    assert f"({'|'.join(atoms)})" in text


def test_opa_classifications_match_policy_schema():
    rego = open(os.path.join(CODE_DIR, "policy", "opa", "data_protection.rego")).read()
    m = re.search(r"allowed_classifications := \{([^}]*)\}", rego)
    assert re.findall(r'"([^"]+)"', m.group(1)) == POLICY["schema"]["keys"]["data-classification"]
