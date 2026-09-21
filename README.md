# headless-sunshine-steam-docker

A Dockerized, headless Linux Sunshine and Steam host built around:

- [Sunshine](https://github.com/LizardByte/Sunshine) — hosts and streams the desktop and games
- [Steam](https://store.steampowered.com/about/) — installs, manages and launches games
- [Heroic](https://heroicgameslauncher.com/) — installs, manages and launches Epic, GOG and Amazon games
- [Moonlight](https://moonlight-stream.org/) — connects clients to the Sunshine host
- NVIDIA NVENC + NvFBC — provides hardware encoding and display capture
- Headless Xorg — creates the virtual display without a physical monitor
- Openbox — provides a lightweight window manager
- Picom — composites the virtual desktop
- PipeWire — provides headless game audio

The goal is to turn a Linux server with an NVIDIA GPU into a console-like Sunshine and Steam appliance with a single command (with prerequisites installed):

```bash
docker compose up -d --build
```

Steam and Heroic are installed automatically (Steam is also bootstrapped/updated on first start). Sunshine starts with a fresh default configuration, and all persistent data is stored under `./data`.

---

## Features

- Fully headless virtual X11 display
- NVIDIA NvFBC capture
- NVIDIA NVENC hardware encoding
- Steam Big Picture / Gamepad UI
- Heroic Desktop and Heroic Console Mode (controller-friendly UI)
- Automatic Steam bootstrap and client updates
- Persistent Steam login, settings and Proton state
- Persistent Sunshine configuration and pairing state
- Automatic Moonlight client-resolution switching
- Mouse, keyboard and controller passthrough through Sunshine
- Selectable NVIDIA GPU for multi-GPU hosts

---

# Prerequisites

You need a Linux host with:

### 1. NVIDIA GPU

A recent NVIDIA GPU with NVENC support is recommended.

This project is designed around NVIDIA's Linux stack and uses **NvFBC** for capture and **NVENC** for encoding.

### 2. NVIDIA driver

Install a recent proprietary NVIDIA driver on the **host**.

The container uses the host kernel driver; the driver itself is not installed inside Docker.

Verify:

```bash
nvidia-smi
```

### 3. Docker Engine + Docker Compose

Install Docker Engine with the Compose plugin:

https://docs.docker.com/engine/install/

Verify:

```bash
docker --version
docker compose version
```

### 4. NVIDIA Container Toolkit

Docker must be able to expose the NVIDIA GPU to containers.

Install NVIDIA Container Toolkit:

https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html

### 5. `/dev/uinput`

Sunshine uses `uinput` for virtual mouse, keyboard and controller devices.

Check:

```bash
ls -l /dev/uinput
```

If it does not exist:

```bash
sudo modprobe uinput
```

This loads the module until the next reboot. To load it automatically on every boot, run once:

```bash
echo uinput | sudo tee /etc/modules-load.d/uinput.conf
```

---

# Installation

## 1. Clone the project

```bash
git clone https://github.com/numsu/headless-sunshine-steam-docker.git
cd headless-sunshine-steam-docker
```

---

## 2. Configure `.env`

Create the environment file:

```bash
cp .env.example .env
```

Set the Sunshine Web UI origin to the LAN address you will use to access Sunshine.

Example:

```dotenv
SUNSHINE_CORS_ORIGIN=https://192.168.1.100:47990
NVIDIA_GPU_ID=0
# Optional: host directory for the game libraries (default: ./data/games)
GAMES_DIR=./data/games
```

Replace `192.168.1.100` with the IP address of your Docker host.

Set `NVIDIA_GPU_ID` to the GPU index reported by `nvidia-smi`; this is normally `0` on a single-GPU server.

You can find the host IP with, for example:

```bash
hostname -I
```

Use a stable/static LAN address if possible.

---

Persistent storage requires no configuration. The default Compose file stores the fresh Sunshine and Steam state in `./data` and all game libraries under `./data/games`.

If you want the game libraries to live in a different host directory, set `GAMES_DIR` in `.env`; otherwise the default is used.

---

# Start the server

Build and start everything:

```bash
docker compose up -d --build
```

Follow the logs:

```bash
docker compose logs -f sunshine-steam
```
On the first start, Steam may take some time to install/update.

---

# Sunshine setup

## 1. Open the Web UI

From another computer on your LAN, open:

```text
https://HOST_IP:47990
```
Sunshine uses a locally generated TLS certificate, so your browser may show a certificate warning. This is expected for a local installation.

Create/login with your Sunshine Web UI credentials.

---

## 2. Configure NVIDIA capture and encoding

In the Sunshine Web UI, open the audio/video configuration.

Recommended values:

```text
Capture: nvfbc
Encoder: nvenc
```
Save the configuration.

---

# Connect Moonlight

## 1. Add the server

Open Moonlight.

Sunshine may be discovered automatically on the LAN.

If it is not, manually add the Docker host IP:

```text
192.168.1.100
```

Do not add port `47990`; Moonlight uses the Sunshine streaming ports automatically.

---

## 2. Pair the client

Select the server in Moonlight.

Moonlight will display a PIN.

Open:

```text
https://HOST_IP:47990
```

In the Sunshine Web UI:

1. Open **PIN**
2. Select the pending pairing request if necessary
3. Enter the PIN shown by Moonlight
4. Give the device a name
5. Confirm

Moonlight should now show the applications published by Sunshine.

Select **Steam Big Picture**, **Steam Desktop**, **Heroic Desktop** or **Heroic Console Mode**.

---

## 3. Set the Moonlight streaming resolution

Configure the desired resolution, FPS and bitrate in the Moonlight client.

The container automatically changes the virtual Xorg desktop to the client-requested resolution when the stream starts.

---

# Networking

The supplied Compose configuration uses host networking so Sunshine discovery and streaming traffic work naturally on the LAN.

Sunshine's default ports include:

| Purpose | Port |
| --- | --- |
| Sunshine HTTPS | TCP 47984 |
| Sunshine HTTP | TCP 47989 |
| Web UI | TCP 47990 |
| RTSP | TCP 48010 |
| Video | UDP 47998 |
| Control | UDP 47999 |
| Audio | UDP 48000 |

If the host firewall blocks these, allow them on your trusted LAN.

Example with UFW:

```bash
sudo ufw allow 47984/tcp
sudo ufw allow 47989/tcp
sudo ufw allow 47990/tcp
sudo ufw allow 48010/tcp
sudo ufw allow 47998/udp
sudo ufw allow 47999/udp
sudo ufw allow 48000/udp
```

Do not blindly expose these ports through your Internet router.

---

# Logs and diagnostics

Follow all container output:

```bash
docker compose logs -f sunshine-steam
```

Check the selected GPU:

```bash
docker compose exec sunshine-steam nvidia-smi
```

Check the virtual display:

```bash
docker compose exec sunshine-steam \
  bash -lc 'DISPLAY=:0 xrandr'
```

Check Sunshine processes:

```bash
docker compose exec sunshine-steam pgrep -a sunshine
```

Check Steam:

```bash
docker compose exec sunshine-steam \
  pgrep -a -f 'steam|steamwebhelper'
```
---

# Recommended Steam settings

Once the system is working, there are a few Steam settings worth changing.

## Enable Vulkan shader pre-caching

Open:

```text
Steam -> Settings -> Downloads
```

Enable:

```text
Enable Shader Pre-Caching
```

and:

```text
Allow background processing of Vulkan shaders
```

The second option is particularly useful for an always-on game server: Steam can process Vulkan shader caches while the machine is idle instead of waiting until game launch.

This can reduce shader-compilation pauses and stutter.

---

## Compatibility / Proton

For Windows-only games:

```text
Game -> Properties -> Compatibility
```

Start with either:

- the current stable Proton release, or
- Proton Experimental

---

## DLSS in Proton/Heroic games (NGX seeding)

DirectX games only offer DLSS when the prefix contains NVIDIA's NGX
loader (`nvngx.dll`, `_nvngx.dll`). Proton copies these from the host
driver directory next to `libGLX_nvidia` (`.../nvidia/wine`), but
nvidia-container-toolkit does not expose that subdir inside the
container — and pressure-vessel can't see it either — so Proton
silently skips the copy and games list only FSR/XeSS.

This image handles it automatically: `NVIDIA_WINE_DIR` (default
`/usr/lib/x86_64-linux-gnu/nvidia/wine`) is bind-mounted read-only at
`/run/host-nvidia-wine`, and the entrypoint seeds every Heroic and Steam
prefix (`/games/Heroic/Prefixes/*/pfx/.../system32`,
`/games/SteamLibrary/steamapps/compatdata/*/pfx/.../system32`) at boot via
`scripts/seed-proton-ngx.sh` (idempotent, 64-bit system32 only, quiet
no-op when the seed is absent). Re-run the seeder manually for prefixes
created while the container is already running:

```bash
docker exec --user root headless-sunshine-steam /usr/local/bin/seed-proton-ngx
```

Find your driver's directory with `dpkg -L libnvidia-gl | grep
'nvidia/wine'` and set `NVIDIA_WINE_DIR` accordingly (the source must
exist — `mkdir -p` an empty dir to disable seeding). Takes effect on
`docker compose up -d --build` (rebuild needed: the seeder ships in
the image); existing prefixes are repaired on next boot, new prefixes
on the boot after they're created.
