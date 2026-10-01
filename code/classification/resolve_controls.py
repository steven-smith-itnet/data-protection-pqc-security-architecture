#!/usr/bin/env python3
"""Resolve the required control set from resource tags (label-to-control mapping).

Takes tags in the shared schema, validates them against label_policy.yaml, and
prints the controls the resource must have: tier, label, protection profile,
controls per data state, per-cloud implementation, and regulatory, domain, and
retention overlays.

Examples
--------
    python resolve_controls.py data-classification=restricted data-domain=payment regulatory-scope=pci_gdpr
    python resolve_controls.py data-classification=confidential data-domain=guest \
        regulatory-scope=gdpr data-owner=guest-platform --cloud azure --json

Exit status: 0 on success, 1 if any tag fails validation.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install pyyaml")

DEFAULT_POLICY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "label_policy.yaml")
KEY_VALUE_RE = re.compile(r"^[a-z0-9_-]+$")
PROFILE_RANK = {"pp1": 1, "pp2": 2, "pp3": 3}


class TagValidationError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def load_policy(path: str = DEFAULT_POLICY) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def parse_tags(pairs: list[str]) -> dict[str, str]:
    tags: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise TagValidationError([f"'{pair}' is not in key=value form"])
        k, v = pair.split("=", 1)
        tags[k.strip()] = v.strip()
    return tags


def validate_tags(tags: dict[str, str], policy: dict) -> tuple[list[str], list[str]]:
    """Return (errors, warnings)."""
    schema = policy["schema"]
    enums = schema["keys"]
    errors: list[str] = []
    warnings: list[str] = []

    for k, v in tags.items():
        if not KEY_VALUE_RE.match(k):
            errors.append(f"tag key '{k}' must be lowercase letters, digits, hyphens, or underscores")
        if not KEY_VALUE_RE.match(v):
            errors.append(f"tag value '{k}={v}' must be lowercase letters, digits, hyphens, or underscores")

    for k in schema["required"]:
        if k not in tags:
            errors.append(f"required tag '{k}' is missing")
    for k in schema.get("recommended", []):
        if k not in tags:
            warnings.append(f"recommended tag '{k}' is missing")

    known = set(enums) | set(schema["free_form"]) | {"regulatory-scope"}
    known.discard("regulatory-scope-atoms")
    for k in tags:
        if k not in known:
            warnings.append(f"tag '{k}' is not part of the schema and is ignored")

    for k, allowed in enums.items():
        if k == "regulatory-scope-atoms" or k not in tags:
            continue
        if tags[k] not in allowed:
            errors.append(f"{k}='{tags[k]}' is not allowed; expected one of: {', '.join(allowed)}")

    for k, pattern in schema["free_form"].items():
        if k in tags and not re.match(pattern, tags[k]):
            errors.append(f"{k}='{tags[k]}' does not match {pattern}")

    if "regulatory-scope" in tags:
        atoms = tags["regulatory-scope"].split("_")
        allowed_atoms = enums["regulatory-scope-atoms"]
        bad = [a for a in atoms if a not in allowed_atoms]
        if bad:
            errors.append(
                f"regulatory-scope='{tags['regulatory-scope']}' contains unknown value(s) {bad}; "
                f"allowed atoms: {', '.join(allowed_atoms)} joined by '_'"
            )
        if "none" in atoms and len(atoms) > 1:
            errors.append("regulatory-scope 'none' cannot be combined with other values")
        if len(set(atoms)) != len(atoms):
            errors.append("regulatory-scope contains duplicate values")

    cls = tags.get("data-classification")
    required_profile = _profile_for_classification(cls, policy) if cls in enums["data-classification"] else None
    pp = tags.get("protection-profile")
    if required_profile and pp in PROFILE_RANK:
        if PROFILE_RANK[pp] < PROFILE_RANK[required_profile]:
            errors.append(
                f"protection-profile='{pp}' is weaker than the {required_profile} required for "
                f"data-classification='{cls}'"
            )
        elif PROFILE_RANK[pp] > PROFILE_RANK[required_profile]:
            warnings.append(f"protection-profile='{pp}' exceeds the {required_profile} minimum; allowed")

    scope_atoms = tags.get("regulatory-scope", "").split("_")
    if "pci" in scope_atoms and cls in ("public", "internal", "confidential"):
        errors.append("regulatory-scope includes pci, which requires data-classification='restricted'")

    return errors, warnings


def _tier_for_classification(cls: str, policy: dict) -> str:
    for tier, spec in policy["tiers"].items():
        if spec["classification"] == cls:
            return tier
    raise KeyError(cls)


def _profile_for_classification(cls: str, policy: dict) -> str:
    return policy["tiers"][_tier_for_classification(cls, policy)]["profile"]


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def profile_controls(profile_id: str, policy: dict) -> dict:
    spec = policy["profiles"][profile_id]
    if "inherits" in spec:
        parent = profile_controls(spec["inherits"], policy)
        spec = _deep_merge(parent, {k: v for k, v in spec.items() if k != "inherits"})
    return spec


def resolve(tags: dict[str, str], policy: dict, cloud: str | None = None, label: str | None = None) -> dict:
    errors, warnings = validate_tags(tags, policy)
    if errors:
        raise TagValidationError(errors)

    cls = tags["data-classification"]
    tier = _tier_for_classification(cls, policy)
    tier_spec = policy["tiers"][tier]
    required_profile = tier_spec["profile"]
    effective_profile = tags.get("protection-profile", required_profile)
    if PROFILE_RANK[effective_profile] < PROFILE_RANK[required_profile]:  # defensive, validated above
        effective_profile = required_profile

    domain = tags.get("data-domain")
    if label:
        if label not in tier_spec["labels"]:
            raise TagValidationError([f"label '{label}' is not valid for tier {tier}; allowed: {tier_spec['labels']}"])
    elif len(tier_spec["labels"]) == 1:
        label = tier_spec["labels"][0]
    else:
        label = policy["label_hints"][cls].get(domain) if domain else None
        label = label or tier_spec["labels"][0]

    controls = profile_controls(effective_profile, policy)
    clouds = controls["clouds"]
    if cloud:
        if cloud not in clouds:
            raise TagValidationError([f"unknown cloud '{cloud}'; expected one of {', '.join(clouds)}"])
        clouds = {cloud: clouds[cloud]}

    overlays: dict[str, list[str]] = {}
    for atom in tags.get("regulatory-scope", "none").split("_"):
        items = policy["overlays"]["regulatory-scope"].get(atom, [])
        if items:
            overlays[f"regulatory-scope:{atom}"] = items
    if domain and domain in policy["overlays"]["data-domain"]:
        overlays[f"data-domain:{domain}"] = policy["overlays"]["data-domain"][domain]
    if "retention-class" in tags:
        overlays[f"retention-class:{tags['retention-class']}"] = [
            policy["overlays"]["retention-class"][tags["retention-class"]]
        ]

    return {
        "tags": tags,
        "warnings": warnings,
        "tier": tier,
        "label": label,
        "protection_profile": effective_profile,
        "profile_name": controls["name"],
        "rating": controls["tier_rating"],
        "common": controls["common"],
        "data_states": controls["data_states"],
        "clouds": clouds,
        "overlays": overlays,
    }


def _fmt(v) -> str:
    if isinstance(v, bool):
        return "required" if v else "not required"
    return str(v)


def render_text(result: dict) -> str:
    lines = []
    lines.append("Tags: " + " ".join(f"{k}={v}" for k, v in result["tags"].items()))
    for w in result["warnings"]:
        lines.append(f"WARNING: {w}")
    lines.append(
        f"Tier: {result['tier']}   Label: {result['label']}   "
        f"Profile: {result['profile_name']} ({result['protection_profile']}, {result['rating']})"
    )
    lines.append("")
    lines.append("Common controls")
    for k, v in result["common"].items():
        lines.append(f"  {k}: {_fmt(v)}")
    for state, items in result["data_states"].items():
        lines.append("")
        lines.append(f"Data {state.replace('_', ' ')}")
        for k, v in items.items():
            lines.append(f"  {k}: {_fmt(v)}")
    for cloud, items in result["clouds"].items():
        lines.append("")
        lines.append(f"Cloud implementation: {cloud}")
        for k, v in items.items():
            lines.append(f"  {k}: {_fmt(v)}")
    for name, items in result["overlays"].items():
        lines.append("")
        lines.append(f"Overlay {name}")
        for item in items:
            lines.append(f"  - {item}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Resolve required controls from data tags.")
    ap.add_argument("tags", nargs="+", help="tags as key=value, e.g. data-classification=restricted")
    ap.add_argument("--policy", default=DEFAULT_POLICY, help="path to label_policy.yaml")
    ap.add_argument("--cloud", choices=["aws", "azure", "gcp", "oci", "on_prem"], help="show one cloud only")
    ap.add_argument("--label", help="explicit sensitivity label, e.g. 'Restricted\\Guest-Identity'")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)

    policy = load_policy(args.policy)
    try:
        tags = parse_tags(args.tags)
        result = resolve(tags, policy, args.cloud, args.label)
    except TagValidationError as exc:
        for e in exc.errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2) if args.json else render_text(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
