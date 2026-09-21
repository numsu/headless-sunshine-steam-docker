#!/bin/bash
# Seed Proton/Wine prefixes with the host NVIDIA NGX loader DLLs.
#
# Proton (Valve and GE builds alike) does NOT bundle nvngx.dll/_nvngx.dll:
# on every prefix setup it copies them from the host driver directory next
# to libGLX_nvidia (…/nvidia/wine). Inside this container that directory is
# absent — nvidia-container-toolkit mounts the .so files but not the wine
# subdir, and pressure-vessel resolves libGLX_nvidia under /run/host where
# the subdir is missing too. The copy is optional, so Proton silently skips
# it and DX11/DX12 games hide their DLSS option (only FSR/XeSS remain).
#
# This script closes the gap: it copies the seed DLLs (bind-mounted from the
# host at /run/host-nvidia-wine, see docker-compose.yml NVIDIA_WINE_DIR)
# into every Heroic prefix's 64-bit system32. Proton never deletes them
# (its own copy is optional and skips when the driver dir is absent), so
# seeding is additive. Safe to run while games are active: the loader is
# read at game start and takes effect on next launch.
#
# Idempotent: files are only touched when missing or hash-different, and a
# missing seed dir (non-NVIDIA host, custom driver layout) exits quietly.
# Only 64-bit system32 is seeded — never copy 64-bit DLLs into syswow64.
set -uo pipefail

SEED_DIR="${NVIDIA_WINE_SEED:-/run/host-nvidia-wine}"
# Default roots cover Heroic and Steam prefixes; pass explicit roots to
# override (e.g. a scratch dir in tests).
if [[ $# -gt 0 ]]; then
    ROOTS=("$@")
else
    ROOTS=(/games/Heroic/Prefixes /games/SteamLibrary/steamapps/compatdata)
fi
FILES="nvngx.dll _nvngx.dll"

[[ -d "$SEED_DIR" ]] || exit 0

have_seed=0
for f in $FILES; do
    [[ -f "$SEED_DIR/$f" ]] && have_seed=1
done
[[ "$have_seed" == 1 ]] || exit 0

seeded=0
shopt -s nullglob
for root in "${ROOTS[@]}"; do
    [[ -d "$root" ]] || continue
    for prefix in "$root"/*/; do
        system32="${prefix}pfx/drive_c/windows/system32"
        [[ -d "$system32" ]] || continue
        for f in $FILES; do
            [[ -f "$SEED_DIR/$f" ]] || continue
            if [[ ! -f "$system32/$f" ]] || ! cmp -s "$SEED_DIR/$f" "$system32/$f"; then
                cp -f "$SEED_DIR/$f" "$system32/$f" \
                    && chown gamer:gamer "$system32/$f" \
                    && echo "seeded $f into $system32" \
                    && seeded=1
            fi
        done
    done
done

[[ "$seeded" == 1 ]] || echo "proton NGX seed: all prefixes already current"
