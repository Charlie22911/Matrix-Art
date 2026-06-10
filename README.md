# Matrix-Art

Matrix-Art is a Raspberry Pi RGB matrix art server for a 64×64 HUB75 LED panel. It provides a browser interface for uploading images and GIFs, drawing pixel art, organizing a library, running Python code effects, managing Wi-Fi or hotspot mode, and tuning matrix timing.

## Project origin and use notice

Matrix-Art was created by its maintainer with assistance from ChatGPT by OpenAI. This notice is included for transparency. OpenAI has not reviewed, tested, certified, or endorsed this project.

Matrix-Art is provided as-is under the GNU General Public License version 2. Installing or running it can change Raspberry Pi boot settings, install a systemd service, adjust audio/module loading, configure networking, and drive GPIO-connected LED matrix hardware. Review the scripts before running them, back up important data, use proper wiring and power equipment, and use the project at your own risk.

To the fullest extent permitted by applicable law, the author is not responsible for damage, data loss, injury, downtime, or other losses arising from installation, wiring, configuration, operation, modification, or use of this project.


Target hardware for the reference build:

- Raspberry Pi Zero 2W
- Adafruit RGB Matrix Bonnet
- 64×64 HUB75 RGB matrix panel, 3 mm pitch
- 5 V DC input through a 5.5 mm OD / 2.1 mm ID barrel jack
- 5 V 4 A minimum power supply

## Features

- Web UI, port chosen during install, default `80`
- Startup IP and port display on the matrix with countdown
- 64×64 image upload, crop, scale, and preview
- Animated GIF upload with crop, scale, frame limit, and live preview
- Browser drawing mode with mouse/touch support, recent colors, eraser, fill, undo, and live matrix preview
- SQLite-backed artwork library
- RGB matrix Python bindings built from the latest `hzeller/rpi-rgb-led-matrix` source during install
- Folder organization, protected folders, Trash, recover, permanent destroy
- Bulk move, bulk delete, folder-level enable/disable
- Slideshow with shuffle, interval, transitions, and transition smoothing
- Code effects written in Python and run from the browser
- Built-in code effects and editable custom code
- Code effects can appear in the normal library and slideshow rotation
- Optional Settings PIN lock with config-file reset recovery
- Wi-Fi station mode and hotspot mode from Settings
- Hotspot fallback when saved Wi-Fi is unavailable
- Matrix timing diagnostics
- Optional CPU isolation support for stable RGB matrix refresh
- Clean systemd shutdown, including running Code effects

## Documentation / Wiki

A page-by-page user manual is included under [`docs/wiki/`](docs/wiki/README.md). It covers each web UI page, including Library, Upload, Draw, Code, Code Help, Settings, Settings PIN, Wi-Fi/Hotspot, installation, hardware, matrix timing, and troubleshooting.

If you want to use GitHub's dedicated Wiki tab, see [`docs/wiki/publishing-github-wiki.md`](docs/wiki/publishing-github-wiki.md).

## Quick install on a fresh Pi

Copy the repository to the Pi, then run:

```bash
cd /home/pi/Matrix-Art
./scripts/install.sh
```

The installer asks for four practical choices:

1. **Web UI port**
   - Default: `80`
   - Change later in `config.toml` under `[server] port`, or from the Settings page.
2. **Adafruit Bonnet hardware PWM jumper**
   - Choose yes if GPIO4 is jumpered to GPIO18 for the Adafruit quality wiring path.
   - When enabled, Matrix-Art uses `gpio_mapping = "adafruit-hat-pwm"`, sets `dtparam=audio=off`, and keeps the Pi onboard audio module from loading because both paths use PWM timing.
   - Choose no for the convenience wiring path without the GPIO4-to-GPIO18 jumper.
3. **CPU isolation and pinning**
   - Default: yes
   - Recommended for a dedicated RGB matrix appliance because it reserves CPU 3 for the panel refresh thread.
4. **Startup mode**
   - Default: install and enable `matrix-art.service` at boot.
   - This is the best default for a headless panel appliance.
   - You can instead install the service but leave it disabled, or skip service installation and run manually.

After install, reboot:

```bash
sudo reboot
```

After reboot, the panel should show its IP address, web port, and countdown. Open:

```text
http://<panel-ip>:<port>/
```

For the default port 80, the browser URL can be shortened to:

```text
http://<panel-ip>/
```

## Non-interactive install examples

Recommended appliance install with defaults:

```bash
./scripts/install.sh --yes
sudo reboot
```

Dry run:

```bash
./scripts/install.sh --dry-run --yes
```

Use port 8080 instead of 80:

```bash
./scripts/install.sh --yes --port 8080
sudo reboot
```

Use convenience wiring without the GPIO4-to-GPIO18 hardware PWM jumper:

```bash
./scripts/install.sh --yes --hardware-pwm no
sudo reboot
```

Install the service file but leave it disabled:

```bash
./scripts/install.sh --yes --service disabled
sudo reboot
```

Manual-run/development style, no service:

```bash
./scripts/install.sh --yes --service none --port 8080
```

Disable CPU isolation and pinning:

```bash
./scripts/install.sh --yes --isolation no
sudo reboot
```

## Maintenance installs

Install or refresh only the RGB matrix driver and Python virtual environment:

```bash
./scripts/install.sh --only-driver --yes
```

Pin the matrix driver to a specific upstream commit instead of latest:

```bash
./scripts/install.sh --only-driver --driver-commit <commit-hash> --yes
```

Install or refresh only the systemd service:

```bash
./scripts/install.sh --only-service --service enable --yes
sudo systemctl restart matrix-art.service
```

## What the installer does

`scripts/install.sh` is the single Matrix-Art installer. It is intended for a fresh Raspberry Pi OS install on the reference Matrix-Art hardware.

The installer performs these tasks:

- Asks for the web UI port, Adafruit hardware PWM jumper status, CPU isolation/pinning preference, and startup mode when run interactively.
- Makes Matrix-Art shell scripts executable.
- Installs required Debian packages with `apt`, including Python, build tools, Pillow, Cython, NetworkManager, Wi-Fi tools, and diagnostics tools.
- Creates a local Python virtual environment in `.venv/`.
- Installs Matrix-Art Python dependencies into that virtual environment.
- Creates runtime directories under `data/`.
- Clones latest `hzeller/rpi-rgb-led-matrix` source into `vendor/rpi-rgb-led-matrix/`.
- Builds and installs the RGB matrix Python bindings into Matrix-Art's `.venv/` with a low-parallelism build so small Pi models are less likely to run out of memory.
- Updates `config.toml` with Matrix-Art defaults for the 64×64 panel, selected web port, selected Adafruit Bonnet mapping, refresh limiting, GPIO slowdown, startup IP display, hotspot fallback, and CPU-affinity settings.
- If hardware PWM is selected, sets `dtparam=audio=off` in the existing Raspberry Pi `config.txt` and writes `/etc/modprobe.d/matrix-art-no-audio.conf` so `snd_bcm2835` stays unloaded.
- Leaves `config.txt` otherwise unchanged.
- Adds Matrix-Art CPU-isolation arguments in the existing `cmdline.txt`, or removes Matrix-Art's own isolation arguments when disabled. If unrelated isolation settings already exist, the installer asks before replacing them.
- Installs, enables, disables, or skips `matrix-art.service`, depending on the selected startup mode.
- Enables NetworkManager so Wi-Fi and hotspot features work from the web UI.
- Runs Python compile checks, shell syntax checks, and an `rgbmatrix` import check.

The installer backs up boot files before it edits the audio or CPU-isolation settings. It also backs up an existing Matrix-Art audio blacklist file before replacing it.

## Why the installer asks about startup mode

For a dedicated headless matrix appliance, installing and enabling the systemd service is the most convenient setup. The panel starts automatically after boot, shows its IP and port, and can be managed from a browser.

For development, it can be useful to install the service but leave it disabled. That lets you test manually with `./run.sh` before enabling boot startup.

Use no-service mode when you want Matrix-Art to be a normal manually launched Python project.

## Why the installer asks about hardware PWM, CPU isolation, and priority

HUB75 RGB matrix panels are continuously refreshed by the Raspberry Pi. The panel does not hold a full image on its own like a normal HDMI display. The Pi has to keep scanning rows and updating PWM timing, so Linux scheduling delays can show up visually as flicker, brightness shimmer, or unstable rows.

Matrix-Art uses several timing measures to reduce flicker.

### Adafruit Bonnet hardware PWM mapping

When the GPIO4-to-GPIO18 jumper is installed, Matrix-Art uses:

```toml
gpio_mapping = "adafruit-hat-pwm"
hardware_pulse = true
```

This matches the Adafruit RGB Matrix Bonnet quality wiring path. It lets the matrix driver use hardware pulse timing. That improves visual stability, but it conflicts with the Raspberry Pi's onboard audio PWM. For that reason, the installer sets `dtparam=audio=off` and blacklists `snd_bcm2835` when hardware PWM mode is selected.

Without the jumper, Matrix-Art uses the convenience mapping:

```toml
gpio_mapping = "adafruit-hat"
hardware_pulse = false
```

### GPIO slowdown and refresh limiting

The default panel timing is:

```toml
slowdown_gpio = 2
limit_refresh_rate_hz = 90
```

`slowdown_gpio` adds small timing delays around GPIO operations. Some HUB75 panels cannot reliably sample the Pi's fastest GPIO transitions. Slowing the GPIO path slightly often removes sparkles, shimmer, or row glitches.

`limit_refresh_rate_hz` asks the matrix driver to use a steadier refresh cadence. A stable 90 Hz refresh can look better than a higher but jittery refresh rate, especially while the Pi is doing web, Wi-Fi, SQLite, GIF, or Code-effect work.

### CPU isolation

When enabled, the installer adds this boot-cmdline pattern on a four-core Pi:

```text
isolcpus=domain,managed_irq,3 nohz_full=3 rcu_nocbs=3 irqaffinity=0,1,2
```

This reserves CPU core 3 for the matrix refresh workload as much as Linux allows:

- `isolcpus=domain,managed_irq,3` keeps normal scheduling and managed IRQs away from core 3.
- `nohz_full=3` reduces periodic scheduler ticks on core 3.
- `rcu_nocbs=3` moves RCU callback work away from core 3.
- `irqaffinity=0,1,2` directs normal interrupts to cores 0-2.

### Thread pinning inside Matrix-Art

The systemd service permits the process to use all four cores:

```ini
CPUAffinity=0 1 2 3
```

Then Matrix-Art does the finer split internally:

- During RGB matrix initialization, Matrix-Art temporarily pins matrix construction to CPU 3.
- The native RGB matrix refresh/PWM thread inherits CPU 3 and realtime scheduling.
- The main Python app, Flask web server, SQLite work, slideshow scheduler, and helper threads are moved back to CPUs 0-2.

The desired result is:

```text
matrix/native refresh thread: CPU 3
web/app/helper work:          CPUs 0-2
normal Linux IRQs:            CPUs 0-2
```

### Realtime priority

The service allows realtime priority:

```ini
LimitRTPRIO=95
LimitNICE=-20
Nice=-10
```

Matrix-Art briefly enters realtime scheduling while constructing the matrix so the native refresh thread can inherit stable timing. The web/app side is then restored to normal scheduling so the browser interface and database work do not run as hard realtime work.

This setup protects the matrix refresh thread without making the whole application compete on the isolated core.

## Normal service commands

```bash
sudo systemctl status matrix-art.service
sudo systemctl restart matrix-art.service
sudo systemctl stop matrix-art.service
journalctl -u matrix-art.service -f
```

## Manual run

```bash
cd /home/pi/Matrix-Art
./run.sh
```

Mock mode for desktop/browser testing without the RGB matrix:

```bash
./scripts/run_mock.sh
```

Mock mode uses port 8080 by default.

## Matrix timing check

```bash
cd /home/pi/Matrix-Art
./scripts/check_matrix_timing.sh
```

The desired result is:

- service CPU affinity allows cores 0-3
- main app/web threads run on cores 0-2
- native matrix refresh thread runs on isolated core 3 when isolation is enabled
- `snd_bcm2835` is not loaded
- `gpio_mapping = "adafruit-hat-pwm"`
- hardware pulse is enabled

## Project layout

```text
matrix_art/                     Python application package
matrix_art/main.py              runtime entry point
matrix_art/database.py          SQLite schema and library logic
matrix_art/artwork/processor.py Pillow processing helpers
matrix_art/display/             RGB matrix, mock display, worker, transitions
matrix_art/slideshow/           slideshow scheduler
matrix_art/demos/               Python Code effect API and runner
matrix_art/web/                 Flask routes, templates, static assets
vendor/rpi-rgb-led-matrix/       driver source cloned during install, ignored by git
.venv/                          Python virtual environment created during install, ignored by git
scripts/install.sh              single installer for dependencies, driver, boot config, and service
scripts/check_matrix_timing.sh  matrix/core-affinity diagnostics
config.toml                     runtime configuration
data/                           runtime database directory, ignored by git
```

## Runtime data

Matrix-Art creates runtime data under:

```text
data/matrix_art.sqlite
```

That database stores artwork, frames, drawings, GIF frames, code effects, folders, settings, Wi-Fi entries, and PIN hashes. It is intentionally ignored by git.

## Notes

Matrix-Art does not commit compiled `rgbmatrix/*.so` files. The installer builds and installs the RGB matrix Python bindings from upstream source on the target Raspberry Pi.

The default installer uses the latest upstream `hzeller/rpi-rgb-led-matrix` commit. For maximum reproducibility, use `./scripts/install.sh --only-driver --driver-commit <commit-hash> --yes`.

## Third-party software and license notices

Matrix-Art uses the Raspberry Pi RGB LED matrix driver originally created by Henner Zeller.
The LED-matrix library is copyright Henner Zeller `<h.zeller@acm.org>` and is licensed under the GNU General Public License Version 2.0 or later.

Matrix-Art also references Adafruit's Raspberry Pi RGB Matrix Bonnet documentation and installer workflow for setup of the Adafruit RGB Matrix Bonnet/HAT.

See `NOTICE`, `LICENSE`, and `licenses/GPL-2.0.txt` for license details.
