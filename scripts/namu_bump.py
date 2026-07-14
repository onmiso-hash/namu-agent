import sys
import os
import re

MANIFEST_PATHS = [
    "namu-plugin/plugin.json",
    "namu-plugin/.claude-plugin/plugin.json"
]

def bump_versions(new_version):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    pattern = re.compile(r'("version"\s*:\s*")([^"]+)(")')

    for path in MANIFEST_PATHS:
        full_path = os.path.join(project_root, path)
        if not os.path.exists(full_path):
            print(f"Warning: {full_path} not found.")
            continue
            
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        new_content = pattern.sub(rf'\g<1>{new_version}\g<3>', content)
        
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        
        print(f"Updated {path} to version {new_version}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python namu_bump.py <new_version>")
        sys.exit(1)
        
    new_version = sys.argv[1]
    bump_versions(new_version)
    print("Done.")
