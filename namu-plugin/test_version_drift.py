import json
import os

MANIFEST_PATHS = [
    "namu-plugin/plugin.json",
    "namu-plugin/.claude-plugin/plugin.json"
]

def test_manifest_versions_match():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    
    versions = []
    
    for path in MANIFEST_PATHS:
        full_path = os.path.join(project_root, path)
        assert os.path.exists(full_path), f"Manifest file not found: {full_path}"
        
        with open(full_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert "version" in data, f"'version' key missing in {path}"
            versions.append((path, data["version"]))
            
    base_path, base_version = versions[0]
    for path, version in versions[1:]:
        assert base_version == version, (
            f"Version mismatch: {base_path} has {base_version}, but {path} has {version}"
        )
