"""Read-only Blender capability probe for the governed free extension stack."""

import json
import sys
from pathlib import Path

import addon_utils
import bpy


CATALOG_PATH = Path(__file__).with_name("free-stack.json")


def operator_exists(identifier):
    if not identifier or "." not in identifier:
        return False
    namespace, operator = identifier.split(".", 1)
    group = getattr(bpy.ops, namespace, None)
    if group is None:
        return False
    return hasattr(group, operator)


def module_state(candidates):
    installed = {module.__name__: module for module in addon_utils.modules()}
    matches = []
    for candidate in candidates:
        for name in installed:
            if candidate.lower() in name.lower() and name not in matches:
                matches.append(name)
    return [
        {
            "module": name,
            "enabled": bool(addon_utils.check(name)[1]),
            "defaultEnabled": bool(addon_utils.check(name)[0]),
        }
        for name in sorted(matches)
    ]


def main():
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    results = []
    for entry in catalog["entries"]:
        operators = {
            identifier: operator_exists(identifier)
            for identifier in entry.get("operatorProbes", [])
        }
        modules = module_state(entry.get("moduleProbes", []))
        results.append(
            {
                "id": entry["id"],
                "declaredMode": entry["mode"],
                "declaredHeadless": entry["headless"],
                "modules": modules,
                "operators": operators,
                "observed": {
                    "installed": bool(modules) or any(operators.values()),
                    "enabled": any(module["enabled"] for module in modules),
                    "allNamedOperatorsPresent": bool(operators) and all(operators.values()),
                },
            }
        )

    report = {
        "schema": "hard-surface-factory.free-blender-stack-probe/1",
        "blender": {
            "version": list(bpy.app.version),
            "versionString": bpy.app.version_string,
            "background": bool(bpy.app.background),
            "binary": bpy.app.binary_path,
        },
        "policy": {
            "readOnly": True,
            "installationAttempted": False,
            "headlessPromotionAutomatic": False,
            "note": "Presence is not context safety. A separate fixture probe and human ruling are required before headless promotion.",
        },
        "entries": results,
    }
    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
