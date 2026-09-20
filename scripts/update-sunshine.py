#!/usr/bin/env python3
"""Update the Dockerfile pin from GitHub's latest stable Sunshine release."""

import json
import os
from pathlib import Path
import re
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
RELEASE_API = "https://api.github.com/repos/LizardByte/Sunshine/releases/latest"
VERSION = r"v[0-9]+(?:\.[0-9]+){2}"
PIN = re.compile(rf"^ARG SUNSHINE_VERSION=({VERSION})$", re.MULTILINE)


def update_pin(dockerfile, release):
    tag = release.get("tag_name", "")
    if release.get("draft") or release.get("prerelease") or not re.fullmatch(VERSION, tag):
        raise ValueError("Expected a stable, versioned Sunshine release")
    pins = PIN.findall(dockerfile)
    if len(pins) != 1:
        raise ValueError("Expected exactly one SUNSHINE_VERSION pin in Dockerfile")
    current = pins[0]
    version_tuple = lambda value: tuple(map(int, value[1:].split(".")))
    if version_tuple(tag) < version_tuple(current):
        raise ValueError(f"Refusing to downgrade Sunshine from {current} to {tag}")
    package = f"sunshine_{tag[1:]}-1+ubuntu24.04_amd64.deb"
    if not any(asset.get("name") == package for asset in release.get("assets", [])):
        raise ValueError(f"Release {tag} is missing required package {package}")
    return PIN.sub(f"ARG SUNSHINE_VERSION={tag}", dockerfile), tag


def main():
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "sunshine-pin-updater"}
    if os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GH_TOKEN']}"
    request = urllib.request.Request(RELEASE_API, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        release = json.load(response)
    path = ROOT / "Dockerfile"
    original = path.read_text(encoding="utf-8")
    updated, tag = update_pin(original, release)
    changed = updated != original
    if changed:
        path.write_text(updated, encoding="utf-8", newline="\n")
    print(f"Sunshine {tag}: {'updated Dockerfile' if changed else 'already current'}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write(f"version={tag}\nchanged={str(changed).lower()}\n")


if __name__ == "__main__":
    main()
