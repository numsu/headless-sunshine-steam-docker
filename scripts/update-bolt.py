#!/usr/bin/env python3
"""Check stable Bolt releases only when ENABLE_BOLT=true."""

import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "https://codeberg.org/Adamcake/Bolt.git"
RELEASE_API = "https://codeberg.org/api/v1/repos/Adamcake/Bolt/releases/latest"


def stable_version(release):
    version = release.get("tag_name", "")
    if (release.get("draft") or release.get("prerelease")
            or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version)):
        raise ValueError("Expected a stable, versioned Bolt release")
    return version


def resolve_commit(version):
    ref = f"refs/tags/{version}"
    result = subprocess.run(
        ["git", "ls-remote", "--exit-code", "--tags", REPOSITORY, ref, ref + "^{}"],
        check=True, capture_output=True, text=True, timeout=60,
    )
    refs = dict(line.split()[::-1] for line in result.stdout.splitlines())
    # Annotated tags must pin the peeled commit, not the tag object's SHA.
    return refs.get(ref + "^{}", refs.get(ref, ""))


def update_pins(dockerfile, release, commit):
    version = stable_version(release)
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Expected a full Bolt commit SHA")
    patterns = {
        "BOLT_VERSION": r"[0-9]+\.[0-9]+\.[0-9]+",
        "BOLT_COMMIT": r"[0-9a-f]{40}",
    }
    pins = {}
    for key, pattern in patterns.items():
        matches = re.findall(rf"^ARG {key}=({pattern})$", dockerfile, re.MULTILINE)
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one {key} pin")
        pins[key] = matches[0]
    if tuple(map(int, version.split('.'))) < tuple(map(int, pins['BOLT_VERSION'].split('.'))):
        raise ValueError("Refusing to downgrade Bolt")
    if version == pins['BOLT_VERSION'] and commit != pins['BOLT_COMMIT']:
        raise ValueError("Existing Bolt tag changed commit; manual review required")
    for key, value in {"BOLT_VERSION": version, "BOLT_COMMIT": commit}.items():
        dockerfile = re.sub(rf"^ARG {key}=.*$", f"ARG {key}={value}", dockerfile, flags=re.MULTILINE)
    return dockerfile, version


def main():
    enabled = os.environ.get("ENABLE_BOLT", "false")
    if enabled not in ("true", "false"):
        raise ValueError("ENABLE_BOLT must be true or false")
    changed, version = False, ""
    if enabled == "true":
        request = urllib.request.Request(RELEASE_API, headers={"User-Agent": "bolt-pin-updater"})
        with urllib.request.urlopen(request, timeout=30) as response:
            release = json.load(response)
        version = stable_version(release)
        commit = resolve_commit(version)
        path = ROOT / "Dockerfile"
        original = path.read_text(encoding="utf-8")
        updated, version = update_pins(original, release, commit)
        changed = updated != original
        if changed:
            path.write_text(updated, encoding="utf-8", newline="\n")
        print(f"Bolt {version}: {'updated Dockerfile' if changed else 'already current'}")
    else:
        print("Bolt check skipped: ENABLE_BOLT=false")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write(f"version={version}\nchanged={str(changed).lower()}\n")


if __name__ == "__main__":
    main()
