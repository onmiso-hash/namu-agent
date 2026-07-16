import json
import os
import re
import sys

MANIFEST_PATHS = [
    "namu-plugin/plugin.json",
    "namu-plugin/.claude-plugin/plugin.json"
]

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def bump_versions(new_version):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    for path in MANIFEST_PATHS:
        full_path = os.path.join(project_root, path)
        if not os.path.exists(full_path):
            print(f"Warning: {full_path} not found.")
            continue

        with open(full_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "version" not in data:
            print(f"Warning: 'version' key missing in {full_path}, skipping.")
            continue

        data["version"] = new_version

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

        print(f"Updated {path} to version {new_version}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python namu_bump.py <new_version>")
        sys.exit(1)

    new_version = sys.argv[1]
    if not VERSION_RE.match(new_version):
        print(f"Error: invalid version format '{new_version}' (expected X.Y.Z)")
        sys.exit(1)

    bump_versions(new_version)
    print("Done.")
