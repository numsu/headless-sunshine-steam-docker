# headless-sunshine-steam-docker

A Dockerized, headless Linux Sunshine and Steam host built around:

- [Sunshine](https://github.com/LizardByte/Sunshine) — hosts and streams the desktop and games
- [Steam](https://store.steampowered.com/about/) — installs, manages and launches games
- [Heroic](https://heroicgameslauncher.com/) — installs, manages and launches Epic, GOG and Amazon games
- [Moonlight](https://moonlight-stream.org/) — connects clients to the Sunshine host
- [Bolt + OSRS](https://codeberg.org/Adamcake/Bolt) - Launcher responsible for OSRS Official and RuneLite Client launching
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

At startup, the container adds `gamer` to the groups owning the exposed uinput,
DRI, and input event/joystick devices. No host-specific group number is needed
in Compose; existing device-node permissions are retained.

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

### 6. `/dev/nvidia-modeset`

The Compose file explicitly exposes NVIDIA's modeset device for Vulkan
presentation to the X11 desktop. It must exist on the host before the container
is created. `NVIDIA_DRIVER_CAPABILITIES=all` alone did not expose this device in
our tested V100 setup. Without it, OpenGL worked but native `vkcube` crashed,
and the Rockstar launcher showed a blank window with Vulkan presentation errors.

Initialize and verify it on the host:

```bash
sudo nvidia-modprobe -m
ls -l /dev/nvidia-modeset
```

If the command is unavailable, install your distribution's `nvidia-modprobe`
package. Do not load kernel modules from inside the container.

For systemd hosts where the device is not already created automatically, the
included service initializes the NVIDIA, UVM, and modeset device nodes before
Docker starts at boot. The unit expects
`nvidia-modprobe` at `/usr/bin/nvidia-modprobe`; check `command -v nvidia-modprobe`
and adjust `ExecStart` if your installation uses a different path.

```bash
sudo install -m 0644 systemd/nvidia-modeset-init.service /etc/systemd/system/nvidia-modeset-init.service
sudo systemctl daemon-reload
sudo systemctl enable --now nvidia-modeset-init.service
```

If updating an already-enabled service, repeat the install and daemon-reload
commands, then run `sudo systemctl restart nvidia-modeset-init.service` to apply
the updated commands immediately. Verify with:

```bash
systemctl status nvidia-modeset-init.service
ls -l /dev/nvidia-modeset
```

After adding the device mapping to an existing installation, close games and
recreate the container (an image rebuild is not required for this mapping):

```bash
docker compose up -d --force-recreate sunshine-steam
docker compose exec sunshine-steam ls -l /dev/nvidia-modeset
```

With Moonlight connected, test Vulkan presentation:

```bash
docker compose exec -u gamer -e DISPLAY=:0 -e XDG_RUNTIME_DIR=/run/user/1000 sunshine-steam timeout 15s vkcube
```

The rotating cube should render for 15 seconds; `timeout` normally returns exit
code 124 when it closes the demo. A missing-device error during container
creation means the host initialization above has not completed successfully.

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

If Xorg rejects the default `DP-0` / 3840×2160 startup mode, set a supported display
identifier and size in `.env`. For example, an installation whose NVIDIA Xorg
log lists `DFP-0` and supports 1080p can use:

```dotenv
XORG_DISPLAY=DFP-0
XORG_WIDTH=1920
XORG_HEIGHT=1080
```

These optional values configure the initial Xorg display at 60 Hz. Other sizes
use CVT reduced-blanking timings. Leaving them unset retains the original display
and 4K modeline. Moonlight resolution switching still detects the active RandR
output (which may have a different name, such as `DVI-D-0`) and requests the
client's stream resolution. The driver must support the selected modes.
Recreate the container after changing these values; when first installing this
feature, rebuild it as well. Correcting a rejected startup mode does not by itself
establish or fix the cause of Vulkan presentation errors.

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

The Dockerfile pins Sunshine with `SUNSHINE_VERSION`. Its Ubuntu package filename
is derived from that version. When choosing a release with a different package
naming convention, also pass `--build-arg SUNSHINE_DEB_NAME=<release-asset-name>`
to `docker compose build`.

## Updating Sunshine

The **Update Sunshine** GitHub Action checks the latest stable upstream release
daily at 10:23 UTC and can also be run from the Actions tab. It verifies that the
Ubuntu 24.04 amd64 package exists, updates `SUNSHINE_VERSION`, builds images with
`ENABLE_BOLT=false` and `ENABLE_BOLT=true`, and opens or updates a single pull request. Prereleases are excluded;
missing packages and build failures fail the run instead of proposing an update.

To enable it, push the workflow to the repository's default branch and enable
**Allow GitHub Actions to create and approve pull requests** under
**Settings > Actions > General > Workflow permissions**. Forks may also need
scheduled workflows enabled in the Actions tab. The workflow uses the built-in
`GITHUB_TOKEN`; no personal access token is required.

After merging an update, pull the changes on the Sunshine host, close any running
games, and rebuild and recreate the container:

```bash
git pull --ff-only
docker compose up -d --build sunshine-steam
docker compose exec sunshine-steam sunshine --version
```

This briefly interrupts streaming. Sunshine settings, pairing state, and games
remain in the persistent `./data` directory. The action does not deploy to the
host. To update the pin locally, run `python3 scripts/update-sunshine.py`.

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

Resolution switching detects the active primary X11 output, or the first active
output when there is no active primary. It works with connector names such as
`DP-0`, `DVI-D-0`, and `HDMI-0`. The requested size comes from Moonlight's streaming
settings, not from automatic detection of the physical client monitor. Choose
the resolution and aspect ratio you want in Moonlight.

The script reuses a mode supported by the selected output and chooses its closest
available refresh rate to the requested FPS. If the size is missing, it attempts
to create and attach a CVT mode; the driver must support that mode. On session
cleanup, it restores the output's previous mode and refresh rate. Restore state
is kept in `/run/user/1000/sunshine-resolution.json` until restoration succeeds.
The existing headless Xorg defaults remain unchanged. With multiple active
outputs, Sunshine's capture output should match the primary output being resized.

To apply resolution-script updates to an existing installation, close games and
run `docker compose up -d --build sunshine-steam`, then start a new Moonlight
session. The existing Sunshine preparation-command paths remain the same.

---

## Add the game library to Steam

The game library is mounted in the container at:

```text
/games
```

Add `/games` as a Steam library.

Normally this can be done from:

```text
Steam -> Settings -> Storage
```

If Steam's Linux Storage UI does not respond to the **Add Drive** button, use the Steam console.

Open the Steam console inside the running graphical session:

```bash
docker compose exec -u gamer sunshine-steam \
  bash -lc 'DISPLAY=:0 steam steam://open/console'
```

Then run in the Steam Console:

```text
library_folder_add /games
```

After that, Steam should see the mounted library normally.

---

# Optional: Old School RuneScape with Bolt

Native Bolt support is experimental and disabled by default. Enable it in `.env`:

```dotenv
ENABLE_BOLT=true
```

Then rebuild and recreate the container:

```bash
docker compose build sunshine-steam
docker compose up -d sunshine-steam
```

The `bolt-builder` stage compiles [Bolt from Codeberg](https://codeberg.org/Adamcake/Bolt)
at the `BOLT_VERSION` and `BOLT_COMMIT` pinned in the Dockerfile, including its pinned
submodules. It uses the committed `app/dist` frontend and builds the CEF C++
wrapper from [Adamcake's native Linux CEF distribution](https://adamcake.com/cef).
The archive is `cef-139.0.7258.139-linux-x86_64-minimal-ungoogled.tar.xz`,
verified with SHA-256
`aeb98ff1f621c8f7c5f0be6c34acefaf4fe4be763004a9d2a9e933d1cd914650`.

Both stages use Ubuntu 24.04. CMake installs Bolt and that same CEF bundle under
`/opt/bolt-launcher`, with its launcher at `/usr/local/bin/bolt`. Only the installed
output is copied into the gaming image; compiler, CMake, Git, source trees, and
development headers stay in the builder. Runtime libraries and OpenJDK 17 for
RuneLite are installed only when enabled. This build supports Linux amd64.
Bolt's optional RuneScape plugin library is omitted; RuneLite plugins are independent.

The build defaults to two compilation jobs to limit memory use. To change it:

```bash
docker compose build --build-arg BOLT_BUILD_JOBS=4 sunshine-steam
```

Bolt and CEF source pins are recorded in `/opt/bolt-launcher/build-info.txt`.
Changing the CEF version also requires updating its checksum and rebuilding Bolt;
do not replace `libcef.so` independently. These pins do not freeze Ubuntu package
repositories or RuneLite's downloaded client updates.

The **Update Bolt** GitHub Action checks stable Codeberg releases daily at
10:43 UTC (or manually from Actions), updates both Bolt pins, and builds with
`ENABLE_BOLT=true` before opening or updating a pull request. It uses the same
GitHub PR permission setting as the Sunshine updater. The workflow explicitly
sets `ENABLE_BOLT=true` because GitHub cannot read your host's `.env`; Docker and
Compose still install Bolt only when you enable that build flag.

The updater leaves the CEF version and checksum pinned. If a new Bolt release
requires a newer CEF bundle, the build must pass after those pins are reviewed
and updated manually. Builds do not replace the launcher checks below.
For a local check, run `ENABLE_BOLT=true python3 scripts/update-bolt.py`.
With the flag unset or false, the updater skips Bolt without contacting Codeberg.

## Validate the native launcher first

Connect to Sunshine's **Desktop** application in Moonlight, then run Bolt as the
existing gamer user inside the running container:

```bash
docker compose exec -u gamer \
  -e DISPLAY=:0 \
  -e XDG_RUNTIME_DIR=/run/user/1000 \
  -e PULSE_SERVER=unix:/run/user/1000/pulse/native \
  sunshine-steam /usr/local/bin/bolt
```

Check that the launcher renders and accepts mouse/keyboard input, sign in with
your Jagex Account, select a character, and launch RuneLite. Close both normally,
recreate the container, and verify settings and login state persist. Bolt's XDG
configuration/data and RuneLite's files remain under the mounted `/home/gamer`.
At startup, the container repairs ownership of the XDG parent directories and
Bolt's own config/data/runtime directories. This also handles directories left
by earlier root-run launcher attempts; it does not recursively change Steam data.
Account login is performed interactively; no credentials belong in the image or
build arguments.

Image builds check shared-library resolution, including GLIBC symbol errors.
A successful build does not validate X11 rendering, CEF subprocess startup,
Jagex login, or RuneLite launch. These require the running server test above.
Adamcake's CEF 139 uses a namespace sandbox; if startup reports sandbox errors,
capture the terminal output before proceeding. This integration adds no sandbox
bypass flags, capabilities, host configuration, or changes to the existing
Compose security settings.

## Launch from Moonlight

When Bolt is installed, container startup registers **Old School RuneScape** in
Sunshine, including installations with an existing persistent app list. Refresh
Moonlight's applications and select **Old School RuneScape**. Startup also removes
equivalent duplicate **Desktop** entries from existing app lists, keeping the first.
Entries with different preparation commands, artwork, or other settings are preserved.
**Low Res Desktop**, **Steam Desktop**, and other launchers remain available.

Registration marks entries it owns with `x-headless-sunshine-steam-managed: bolt`.
It also recognizes this branch's earlier entry by its exact Bolt launch command
and bundled cover path. Independently configured applications are preserved.
If an independent **Old School RuneScape** entry already exists, registration
leaves it untouched and logs the name conflict; rename that entry to allow
automatic Bolt registration.

For a managed entry, registration preserves custom artwork and settings, clears
**Command**, and updates **Detached Command** to launch Bolt directly and record
startup errors. Default desktop artwork is replaced with the bundled Bolt × RS cover:

```text
setsid env DISPLAY=:0 /usr/local/bin/bolt >> /home/gamer/.local/state/bolt-launcher.log 2>&1
```

Global preparation commands are enabled by default for resolution switching. Bolt inherits
the existing gamer session's runtime and audio environment. A detached application
continues running after the stream ends; close RuneLite and Bolt from the desktop
when finished.

## Reopen apps from the desktop

Right-click an empty area of the streamed desktop to open the gaming menu:

- **Steam Desktop** opens the Steam library.
- **Steam Big Picture** opens Steam's gamepad interface.
- **Bolt Launcher** appears when Bolt is installed (`ENABLE_BOLT=true`).
- **Windows** lists open windows, including minimized clients you can restore.
- **Reload Openbox Configuration** reloads the desktop configuration.

The menu has no **Exit** action. Closing Steam or Bolt leaves the desktop menu
available to launch them again. Launchers run as the existing gamer session user.

At session startup, `/run/user/1000/openbox-menu.xml` is generated and selected
in the session's Openbox configuration. It replaces the distro or saved menu for
that session; saved menu files remain untouched. Rebuild and recreate the
container after updating to receive this menu in an existing installation.

## Arrange multiple game clients

The streamed desktop runs Openbox and explicitly enables its title bars and
borders for normal application windows, including windowed game clients. Drag
the title bar to move a client, or drag its borders to resize it. Fullscreen
windows still need to be switched to windowed mode to show decorations.

Rebuild and recreate the container to apply this to an existing installation
(this stops the current session, so close your games first):

```bash
docker compose up -d --build sunshine-steam
```

Each session derives `/run/user/1000/openbox-rc.xml` from the saved
`/home/gamer/.config/openbox/rc.xml`, or the image's default configuration when
there is no saved file. It adds a final rule enabling decorations for normal
windows and selects the gaming menu. Your saved file is not modified; other
settings and bindings are kept.
Applications with their own title bars may display both their own bar and the
Openbox bar.

With the default
[Openbox controls](https://openbox.org/help/DefaultConfiguration), use:

- **Alt + left mouse drag** anywhere inside a window to move it.
- **Alt + right mouse drag** inside a window to resize it.
- **Alt + Space** to open the focused window's menu, including move, resize,
  and maximize/restore controls.
- **Alt + Tab** to switch between open windows, including Bolt and game clients.

For two accounts, launch each character's client through Bolt, keep both clients
in windowed mode, and resize and move them beside each other in the same stream.
Restore maximized windows before arranging them. Client minimum sizes can limit
how small each window can become; increase the Moonlight streaming resolution
if both do not fit. These controls arrange windows; each client receives manual
input when focused.

These shortcuts require Moonlight to pass the keys to the host and assume the
default Openbox bindings. If Alt-drag has no effect, check that Openbox is running:

```bash
docker compose exec -u gamer sunshine-steam pgrep -a openbox
```

A saved `/home/gamer/.config/openbox/rc.xml` (host path
`./data/.config/openbox/rc.xml`) can override the default shortcuts. Check that
file and the container logs if window controls are missing. If configuration
generation fails for a saved configuration, startup logs the error and applies
the gaming menu and title-bar rule to the image's default configuration instead.

## Troubleshoot the Bolt application

The app object is provided in `sunshine-config/osrs-app.json`. Registration does
not prove Bolt can launch: complete the native validation above. If Moonlight
shows only the desktop after selecting **Old School RuneScape**, read the log:

```bash
docker compose exec -u gamer sunshine-steam \
  tail -n 100 /home/gamer/.local/state/bolt-launcher.log
```

If the log is missing, confirm the image was rebuilt with `ENABLE_BOLT=true`
and the container recreated, then inspect the app's Detached Command in Sunshine.
To see startup errors directly, use the foreground native-launch command above.
Changing `.env` followed by `docker compose restart` does not rebuild the image.

With `ENABLE_BOLT=false` (the default), the build skips Bolt/CEF downloads and
compilation, extra runtime dependencies, and the Bolt home helper, cover, and
Sunshine app template. Startup removes only this integration's managed Bolt
entries from the persistent Sunshine app list. Saved Bolt/RuneLite data
remains intact; enabling Bolt again restores the app entry.

After changing the flag in `.env`, rebuild and recreate the container:

```bash
docker compose up -d --build --force-recreate sunshine-steam
```

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

## Container fails after reboot: missing `/dev/nvidia-modeset`

If Docker fails to start the container with:

```text
error gathering device information while adding custom device "/dev/nvidia-modeset": no such file or directory
```

Check the NVIDIA driver and device node on the **host**:

```bash
nvidia-smi
lsmod | grep nvidia
ls -l /dev/nvidia-modeset
```

On headless NVIDIA hosts, the `nvidia_modeset` kernel module may be loaded while
the corresponding device node has not yet been created. This was observed after
a reboot on Debian 13 with Tesla V100 GPUs, even though `nvidia-smi` worked and
the other NVIDIA modules and device nodes were present.

If the driver is otherwise healthy and the modeset module is loaded but
`/dev/nvidia-modeset` is missing, create it and retry startup:

```bash
sudo nvidia-modprobe -m
ls -l /dev/nvidia-modeset
docker compose up -d sunshine-steam
```

For subsequent reboots, install and enable the
[host initialization service](#6-devnvidia-modeset) described in the prerequisites.
If it is already installed, inspect its boot log with
`sudo journalctl -b -u nvidia-modeset-init.service`.

Keep the `/dev/nvidia-modeset` mapping in Compose: `/dev/nvidia0` serves a
different purpose and is not a replacement. The node must exist before Docker
starts the container; a check inside the container would run too late.

## Container diagnostics

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
