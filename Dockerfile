# syntax=docker/dockerfile:1.7

FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive

# Pin Sunshine and Heroic for reproducible builds.
ARG SUNSHINE_VERSION=v2026.516.143833
ARG HEROIC_VERSION=v2.22.3

ENV NVIDIA_DRIVER_CAPABILITIES=all

# Install Steam and the graphics, desktop and audio dependencies.

RUN dpkg --add-architecture i386 \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        software-properties-common \
    && add-apt-repository -y multiverse \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        \
        # X11
        xserver-xorg-core \
        xserver-xorg-input-libinput \
        x11-xserver-utils \
        x11-utils \
        xcvt \
        mesa-utils \
        vulkan-tools \
        \
        # Desktop/window management
        openbox \
        picom \
        wmctrl \
        xdotool \
        \
        # User session
        dbus-x11 \
        tini \
        procps \
        psmisc \
        \
        # Audio
        pipewire \
        pipewire-pulse \
        pipewire-audio \
        wireplumber \
        pulseaudio-utils \
        \
        # Steam
        steam-installer \
        steam-devices \
        \
        # 32-bit Steam libraries
        libxtst6:i386 \
        libgtk2.0-0:i386 \
        libpipewire-0.3-0:i386 \
        libxcb-res0:i386 \
        libgl1:i386 \
        libglx0:i386 \
        libegl1:i386 \
        libvulkan1:i386 \
        \
        # Controller diagnostics
        joystick \
    && rm -rf /var/lib/apt/lists/*

# Ubuntu installs the Steam launcher under /usr/games.
RUN ln -sf /usr/games/steam /usr/local/bin/steam

# Install Sunshine.
RUN curl -fL \
        "https://github.com/LizardByte/Sunshine/releases/download/${SUNSHINE_VERSION}/sunshine-ubuntu-24.04-amd64.deb" \
        -o /tmp/sunshine.deb \
    && apt-get update \
    && apt-get install -y /tmp/sunshine.deb \
    && rm -f /tmp/sunshine.deb \
    && rm -rf /var/lib/apt/lists/*

# Install Heroic Games Launcher (Epic/GOG/Amazon) from its official .deb.
# The .deb installs the Electron app under /opt/Heroic with a
# /usr/share/applications/heroic.desktop entry (Exec=/opt/Heroic/heroic).
RUN curl -fL \
        "https://github.com/Heroic-Games-Launcher/HeroicGamesLauncher/releases/download/${HEROIC_VERSION}/Heroic-${HEROIC_VERSION#v}-linux-amd64.deb" \
        -o /tmp/heroic.deb \
    && apt-get update \
    && apt-get install -y /tmp/heroic.deb \
    && rm -f /tmp/heroic.deb \
    && rm -rf /var/lib/apt/lists/*

# Expose Heroic on PATH (mirrors the steam symlink above) so Sunshine's
# detached commands can invoke it, and seed Sunshine's assets with the
# Heroic cover art so "image-path": "heroic.png" resolves to a real icon.
RUN ln -sf /opt/Heroic/heroic /usr/local/bin/heroic \
    && for size in 512x512 256x256 128x128 64x64; do \
        if [ -f "/usr/share/icons/hicolor/${size}/apps/heroic.png" ]; then \
            cp "/usr/share/icons/hicolor/${size}/apps/heroic.png" /usr/share/sunshine/heroic.png; \
            break; \
        fi; \
    done \
    && test -f /usr/share/sunshine/heroic.png

COPY --chmod=0644 sunshine-config/apps.json /usr/local/share/headless-sunshine-steam/apps.json
COPY --chmod=0644 heroic-config.json /usr/local/share/headless-sunshine-steam/heroic-config.json

# Create the user that owns the persistent home directory.
RUN set -eux; \
    existing_user="$(getent passwd 1000 | cut -d: -f1 || true)"; \
    existing_group="$(getent group 1000 | cut -d: -f1 || true)"; \
    \
    if [ -n "$existing_group" ] && [ "$existing_group" != "gamer" ]; then \
        groupmod -n gamer "$existing_group"; \
    elif [ -z "$existing_group" ]; then \
        groupadd --gid 1000 gamer; \
    fi; \
    \
    if [ -n "$existing_user" ] && [ "$existing_user" != "gamer" ]; then \
        usermod \
            --login gamer \
            --home /home/gamer \
            --move-home \
            --shell /bin/bash \
            "$existing_user"; \
    elif [ -z "$existing_user" ]; then \
        useradd \
            --uid 1000 \
            --gid 1000 \
            --create-home \
            --shell /bin/bash \
            gamer; \
    fi

RUN install -d -o gamer -g gamer \
      /home/gamer/.config \
      /home/gamer/.local \
      /home/gamer/.local/share \
      /home/gamer/.local/state \
      /home/gamer/.cache

WORKDIR /home/gamer

# Generate a headless Xorg configuration for the exposed NVIDIA GPU.
RUN cat > /usr/local/bin/generate-xorg-config <<'EOF'
#!/bin/bash
set -euo pipefail

GPU_BDF="$(nvidia-smi --query-gpu=pci.bus_id --format=csv,noheader | head -n1)"

if [[ -z "$GPU_BDF" ]]; then
    echo "No NVIDIA GPU visible inside container." >&2
    exit 1
fi

IFS=':.' read -r DOMAIN BUS SLOT FUNCTION <<< "$GPU_BDF"

BUS_DEC=$((16#$BUS))
SLOT_DEC=$((16#$SLOT))
FUNCTION_DEC=$((16#$FUNCTION))

XORG_BUS_ID="PCI:${BUS_DEC}:${SLOT_DEC}:${FUNCTION_DEC}"

mkdir -p /etc/X11/xorg.conf.d

cat > /etc/X11/xorg.conf.d/20-nvidia.conf <<XORG
Section "ServerLayout"
    Identifier "HeadlessLayout"
    Screen 0 "Screen0"
EndSection

Section "Monitor"
    Identifier "Monitor0"
    HorizSync 30-160
    VertRefresh 30-120

    Modeline "3840x2160_60" 533.25 3840 3888 3920 4000 2160 2163 2168 2222 +HSync -VSync

    Option "Enable" "true"
EndSection

Section "Device"
    Identifier "Device0"
    Driver "nvidia"
    BusID "${XORG_BUS_ID}"

    Option "AllowEmptyInitialConfiguration" "True"

    Option "ConnectedMonitor" "DP-0"
    Option "UseDisplayDevice" "DP-0"
    Option "UseEDID" "False"

    Option "ModeValidation" "NoEdidModes,NoDFPNativeResolutionCheck,NoVirtualSizeCheck,NoMaxPClkCheck,NoHorizSyncCheck,NoVertRefreshCheck"

    Option "MetaModes" "DP-0: 3840x2160_60 +0+0"

    Option "Coolbits" "4"
EndSection

Section "Screen"
    Identifier "Screen0"
    Device "Device0"
    Monitor "Monitor0"
    DefaultDepth 24

    SubSection "Display"
        Depth 24
        Modes "3840x2160_60"
        Virtual 3840 2160
    EndSubSection
EndSection
XORG

echo "Configured Xorg on ${GPU_BDF} as ${XORG_BUS_ID}"
EOF

RUN chmod +x /usr/local/bin/generate-xorg-config

# Switch the virtual display to the resolution requested by the client.
RUN cat > /usr/local/bin/sunshine-resolution-do <<'EOF'
#!/bin/bash
set -euo pipefail

export DISPLAY=:0

W="${SUNSHINE_CLIENT_WIDTH:-3840}"
H="${SUNSHINE_CLIENT_HEIGHT:-2160}"
FPS="${SUNSHINE_CLIENT_FPS:-60}"

BASE_MODE="${W}x${H}"

# Prefer a mode the NVIDIA driver already exposes.
if xrandr | grep -qE "^[[:space:]]+${BASE_MODE}[[:space:]]"; then
    xrandr --output DP-0 --mode "$BASE_MODE"
    exit 0
fi

MODELINE="$(cvt "$W" "$H" "$FPS" | grep '^Modeline')"
NAME="$(awk '{print $2}' <<< "$MODELINE" | tr -d '"')"

# The same dynamically-created mode may already exist from a previous stream.
if ! xrandr --query | grep -qE "^[[:space:]]+${NAME}[[:space:]]"; then
    read -r CLOCK H1 H2 H3 H4 V1 V2 V3 V4 HSYNC VSYNC <<< \
        "$(awk '{print $3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13}' <<< "$MODELINE")"

    xrandr --newmode \
        "$NAME" "$CLOCK" \
        "$H1" "$H2" "$H3" "$H4" \
        "$V1" "$V2" "$V3" "$V4" \
        "$HSYNC" "$VSYNC"
fi

# It may exist globally but not yet be associated with DP-0.
xrandr --addmode DP-0 "$NAME" 2>/dev/null || true

xrandr --output DP-0 --mode "$NAME"
EOF

RUN chmod +x /usr/local/bin/sunshine-resolution-do

RUN cat > /usr/local/bin/sunshine-resolution-undo <<'EOF'
#!/bin/bash

export DISPLAY=:0

# Sunshine runs this undo command synchronously on every app quit and waits
# for it without a timeout, so it must never block. Only ask Steam to shut
# down when a client is actually running: invoking `steam -shutdown` with no
# client active launches Steam (including slow update downloads), which hangs
# Moonlight's quit request until the container is restarted.
if pgrep -x steam >/dev/null 2>&1; then
    timeout --signal=TERM --kill-after=5s 15s steam -shutdown >/dev/null 2>&1 || true
fi

EOF

RUN chmod +x /usr/local/bin/sunshine-resolution-undo

# Tracked launcher for the Heroic Games Launcher.
#
# Sunshine runs this as the app's main command inside its own process group,
# so Moonlight Quit (SIGTERM to the group, SIGKILL after exit-timeout) always
# reaches Heroic. Do NOT use setsid here: detaching would move Heroic into a
# new session outside Sunshine's process group, leaving it running after quit
# and wedging the session. Extra args (e.g. --console) pass through to Heroic.
RUN cat > /usr/local/bin/launch-heroic <<'EOF'
#!/bin/bash
set -uo pipefail

export DISPLAY="${DISPLAY:-:0}"

HEROIC_PID=""

stop_heroic() {
    if [[ -n "$HEROIC_PID" ]] && kill -0 "$HEROIC_PID" 2>/dev/null; then
        kill -TERM "$HEROIC_PID" 2>/dev/null || true
    fi
}

trap stop_heroic TERM INT

/opt/Heroic/heroic "$@" &
HEROIC_PID=$!

# A trapped signal interrupts wait, so loop until Heroic is actually gone.
while kill -0 "$HEROIC_PID" 2>/dev/null; do
    wait "$HEROIC_PID" 2>/dev/null || true
done

exit 0
EOF

RUN chmod +x /usr/local/bin/launch-heroic

# Register the shared Steam library (/games/SteamLibrary) in the Steam
# client's libraryfolders.vdf, so users do not have to import it manually
# from Steam settings. The current client keeps that file at
# ~/.steam/debian-installation/config/libraryfolders.vdf.
#
# Safety rules:
#   * Idempotent - an existing registration leaves the file untouched.
#   * A file with an unrecognized structure is left untouched.
#   * Only meant to run at boot, while no Steam process is running.
COPY --chmod=0755 scripts/steam-register-library.py /usr/local/bin/steam-register-library

# Seed Proton prefixes with the host NVIDIA NGX loader (see the script
# header for why). Invoked from container-entrypoint at boot; safe to
# re-run manually any time with: docker exec --user root <container>
# /usr/local/bin/seed-proton-ngx
COPY --chmod=0755 scripts/seed-proton-ngx.sh /usr/local/bin/seed-proton-ngx


# Start the graphical and audio session.
RUN cat > /usr/local/bin/gaming-session <<'EOF'
#!/bin/bash
set -euo pipefail

export DISPLAY=:0
export XDG_RUNTIME_DIR=/run/user/1000
export PULSE_SERVER=unix:/run/user/1000/pulse/native

PIDS=()

cleanup() {
    for pid in "${PIDS[@]:-}"; do
        kill "$pid" 2>/dev/null || true
    done
}

trap cleanup EXIT TERM INT

pipewire &
PIDS+=("$!")

sleep 0.2

pipewire-pulse &
PIDS+=("$!")

wireplumber &
PIDS+=("$!")

# Wait for PulseAudio compatibility server.
for _ in $(seq 1 50); do
    pactl info >/dev/null 2>&1 && break
    sleep 0.1
done

# Permanent fallback audio sink for headless operation.
if ! pactl list short sinks | awk '{print $2}' | grep -qx headless; then
    pactl load-module module-null-sink \
        sink_name=headless \
        sink_properties=device.description=Headless
fi

pactl set-default-sink headless

openbox &
PIDS+=("$!")

picom --backend glx &
PIDS+=("$!")

sunshine &
SUNSHINE_PID="$!"
PIDS+=("$SUNSHINE_PID")

wait "$SUNSHINE_PID"
EOF

RUN chmod +x /usr/local/bin/gaming-session

RUN cat > /usr/local/bin/container-entrypoint <<'EOF'
#!/bin/bash
set -euo pipefail

GAMER_UID=1000
GAMER_USER=gamer
GAMER_HOME=/home/gamer

# Match the gamer user to host device-node groups dynamically.

add_device_group() {
    local path="$1"

    [[ -e "$path" ]] || return 0

    local gid
    local group

    gid="$(stat -c '%g' "$path")"
    group="$(getent group "$gid" | cut -d: -f1 || true)"

    if [[ -z "$group" ]]; then
        group="hostdev-${gid}"
        groupadd --gid "$gid" "$group"
    fi

    usermod -aG "$group" "$GAMER_USER"
}

add_device_group /dev/uinput
add_device_group /dev/input
add_device_group /dev/dri

for device in /dev/dri/card* /dev/dri/renderD*; do
    [[ -e "$device" ]] && add_device_group "$device"
done

# Avoid recursively changing ownership of persistent Steam data.
mkdir -p "$GAMER_HOME"
chown "$GAMER_USER:$GAMER_USER" "$GAMER_HOME"
chown "$GAMER_USER:$GAMER_USER" /games

# Seed the standard XDG directories and ensure they belong to the gamer
# user. A fresh persistent home can otherwise leave e.g. ~/.config owned by
# root (created while installing Sunshine's managed files), which makes GUI
# apps launched as gamer fail at startup because they cannot create their
# own config subdirectories.
# Only the top-level directories are chowned, never their contents.
mkdir -p \
    "$GAMER_HOME/.config" \
    "$GAMER_HOME/.local/share" \
    "$GAMER_HOME/.local/state" \
    "$GAMER_HOME/.cache"
chown "$GAMER_USER:$GAMER_USER" \
    "$GAMER_HOME/.config" \
    "$GAMER_HOME/.local" \
    "$GAMER_HOME/.local/share" \
    "$GAMER_HOME/.local/state" \
    "$GAMER_HOME/.cache"

# The shared /games mount holds every game library in one place:
# /games/SteamLibrary for Steam and /games/Heroic for Heroic
# (Epic/GOG/Amazon installs and Wine prefixes). The steamapps/ subdirectory
# marks SteamLibrary as a valid Steam library folder - without it the client
# drops the entry from libraryfolders.vdf on first launch.
mkdir -p /games/SteamLibrary/steamapps /games/Heroic
chown "$GAMER_USER:$GAMER_USER" /games/SteamLibrary /games/SteamLibrary/steamapps /games/Heroic

# Migrate Heroic data out of the Steam library for setups created before
# /games became the shared parent (back then /games was the Steam library
# itself, so Heroic lived at /games/Heroic == <old-library>/Heroic). Only
# moves when the new location is still empty, so existing data is never
# merged over or deleted; same-filesystem rename, nothing is copied.
LEGACY_HEROIC=/games/SteamLibrary/Heroic

if [[ -d "$LEGACY_HEROIC" ]] \
    && [[ -z "$(ls -A /games/Heroic)" ]] \
    && [[ -n "$(ls -A "$LEGACY_HEROIC")" ]]; then
    echo "Migrating legacy Heroic library $LEGACY_HEROIC to /games/Heroic..."
    mv "$LEGACY_HEROIC"/* "$LEGACY_HEROIC"/.* /games/Heroic/ 2>/dev/null || true
    rmdir --ignore-fail-on-non-empty "$LEGACY_HEROIC" 2>/dev/null || true
fi

# Seed Heroic's default install/prefix locations without ever touching
# existing user settings (Heroic merges these factory-style defaults under
# stored values on launch).
HEROIC_CONF_DIR="$GAMER_HOME/.config/heroic"
HEROIC_CONF="$HEROIC_CONF_DIR/config.json"

install -d \
    --owner="$GAMER_USER" \
    --group="$GAMER_USER" \
    "$HEROIC_CONF_DIR"

if [[ ! -e "$HEROIC_CONF" ]]; then
    install \
        --owner="$GAMER_USER" \
        --group="$GAMER_USER" \
        --mode=0644 \
        /usr/local/share/headless-sunshine-steam/heroic-config.json \
        "$HEROIC_CONF"
fi

# Clean up the legacy ~/Games/Heroic seed from earlier images, but only when
# empty so existing game data is never touched.
rmdir --ignore-fail-on-non-empty "$GAMER_HOME/Games/Heroic" 2>/dev/null || true
rmdir --ignore-fail-on-non-empty "$GAMER_HOME/Games" 2>/dev/null || true

# Seed every Heroic prefix with the host NVIDIA NGX loader so DX games can
# expose DLSS (missing seed dir or prefixes: quiet no-op). Best-effort on
# purpose: a stale or absent driver layout must never wedge boot.
if [[ -x /usr/local/bin/seed-proton-ngx ]]; then
    /usr/local/bin/seed-proton-ngx || true
fi

install -d \
    --owner="$GAMER_USER" \
    --group="$GAMER_USER" \
    --mode=0700 \
    /run/user/1000

generate-xorg-config

Xorg :0 \
    -noreset \
    -nolisten tcp \
    -ac \
    >/var/log/Xorg.0.log 2>&1 &

XORG_PID="$!"

cleanup() {
    kill "$SESSION_PID" 2>/dev/null || true
    kill "$XORG_PID" 2>/dev/null || true
}

SESSION_PID=""

trap cleanup TERM INT EXIT

for _ in $(seq 1 100); do
    if DISPLAY=:0 xrandr >/dev/null 2>&1; then
        break
    fi

    if ! kill -0 "$XORG_PID" 2>/dev/null; then
        echo "Xorg exited unexpectedly:" >&2
        tail -100 /var/log/Xorg.0.log >&2 || true
        exit 1
    fi

    sleep 0.1
done

if ! DISPLAY=:0 xrandr >/dev/null 2>&1; then
    echo "Xorg did not become ready." >&2
    tail -100 /var/log/Xorg.0.log >&2 || true
    exit 1
fi

# Sunshine managed settings
# Only the Web UI origin and resolution commands are managed automatically.

SUNSHINE_DIR="${GAMER_HOME}/.config/sunshine"
SUNSHINE_CONF="${SUNSHINE_DIR}/sunshine.conf"

install -d \
    --owner="$GAMER_USER" \
    --group="$GAMER_USER" \
    "$SUNSHINE_DIR"

if [[ ! -e "${SUNSHINE_DIR}/apps.json" ]]; then
    install \
        --owner="$GAMER_USER" \
        --group="$GAMER_USER" \
        --mode=0644 \
        /usr/local/share/headless-sunshine-steam/apps.json \
        "${SUNSHINE_DIR}/apps.json"
fi

touch "$SUNSHINE_CONF"

TMP="$(mktemp)"

awk \
    -v origin="${SUNSHINE_CORS_ORIGIN:-}" \
    -v prep='[{"do":"/usr/local/bin/sunshine-resolution-do","undo":"/usr/local/bin/sunshine-resolution-undo"}]' '
    BEGIN {
        cors_replaced = 0
        prep_replaced = 0
    }

    /^[[:space:]]*csrf_allowed_origins[[:space:]]*=/ {
        if (origin == "") {
            print
        } else if (!cors_replaced) {
            print "csrf_allowed_origins = " origin
            cors_replaced = 1
        }
        next
    }

    /^[[:space:]]*global_prep_cmd[[:space:]]*=/ {
        if (!prep_replaced) {
            print "global_prep_cmd = " prep
            prep_replaced = 1
        }
        next
    }

    {
        print
    }

    END {
        if (origin != "" && !cors_replaced) {
            print "csrf_allowed_origins = " origin
        }

        if (!prep_replaced) {
            print "global_prep_cmd = " prep
        }
    }
' "$SUNSHINE_CONF" > "$TMP"

cat "$TMP" > "$SUNSHINE_CONF"
rm -f "$TMP"

chown "$GAMER_USER:$GAMER_USER" "$SUNSHINE_CONF"

# Bootstrap or update Steam inside the persistent home directory.
mkdir -p /tmp/steam-headless-bin

cat > /tmp/steam-headless-bin/zenity <<'ZENITY'
#!/bin/sh
exit 0
ZENITY

chmod 0755 /tmp/steam-headless-bin/zenity

STEAM_CLIENT="${GAMER_HOME}/.steam/debian-installation/ubuntu12_32/steam"

shutdown_steam() {
    local status

    timeout --signal=TERM --kill-after=1s 5s \
        su - "$GAMER_USER" -c \
        'PATH="/tmp/steam-headless-bin:/usr/local/bin:/usr/games:/usr/bin:/bin" DISPLAY=:0 steam -shutdown' \
        && return 0

    status=$?

    if [[ "$status" -eq 124 || "$status" -eq 137 ]]; then
        echo "Steam shutdown timed out after 5 seconds; continuing."
    else
        echo "Steam shutdown exited with status ${status}; continuing."
    fi
}

if [[ ! -x "$STEAM_CLIENT" ]]; then
    echo "Steam client missing; bootstrapping into ${GAMER_HOME}..."

    su - "$GAMER_USER" -c \
        'PATH="/tmp/steam-headless-bin:/usr/local/bin:/usr/games:/usr/bin:/bin" DISPLAY=:0 steam -silent' &

    STEAM_BOOTSTRAP_PID="$!"

    for _ in $(seq 1 600); do
        [[ -x "$STEAM_CLIENT" ]] && break

        if ! kill -0 "$STEAM_BOOTSTRAP_PID" 2>/dev/null; then
            break
        fi

        sleep 1
    done

    if [[ ! -x "$STEAM_CLIENT" ]]; then
        echo "Steam bootstrap did not complete." >&2
        exit 1
    fi

    # Give the updater a moment to finish committing files.
    sleep 5

    shutdown_steam

    kill "$STEAM_BOOTSTRAP_PID" 2>/dev/null || true
    sleep 1
    kill -KILL "$STEAM_BOOTSTRAP_PID" 2>/dev/null || true

    wait "$STEAM_BOOTSTRAP_PID" 2>/dev/null || true
else
    echo "Checking Steam client installation/update..."

    # Run the updater without leaving Steam active before Sunshine starts it.
    shutdown_steam
fi

# Do not let an updater-owned Steam process leak into the Sunshine session.
for _ in $(seq 1 10); do
    if ! pgrep -u "$GAMER_UID" -x steam >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

pkill -KILL -u "$GAMER_UID" -x steam 2>/dev/null || true

# Register the shared Steam library (/games/SteamLibrary) in the client's
# libraryfolders.vdf. Safe here: no Steam process is running, the operation
# is idempotent, and an unrecognized file is left untouched.
/usr/local/bin/steam-register-library

su - "$GAMER_USER" -c \
    'exec dbus-run-session -- /usr/local/bin/gaming-session' &

SESSION_PID="$!"

wait "$SESSION_PID"
EOF

RUN chmod +x /usr/local/bin/container-entrypoint

EXPOSE 47984/tcp
EXPOSE 47989/tcp
EXPOSE 47990/tcp
EXPOSE 48010/tcp

EXPOSE 47998/udp
EXPOSE 47999/udp
EXPOSE 48000/udp

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/container-entrypoint"]
