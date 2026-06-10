# Matrix-Art

Matrix-Art turns a Raspberry Pi and a 64×64 HUB75 RGB LED matrix into a browser-controlled art appliance. It supports image and GIF uploads, pixel drawing, slideshow playback, Python-generated effects, Wi-Fi/hotspot management, and matrix timing diagnostics.

## Reference hardware

Matrix-Art is built around this reference setup:

- Raspberry Pi Zero 2W
- Adafruit RGB Matrix Bonnet
- 64×64 HUB75 RGB matrix panel, 3 mm pitch
- 5 V DC input through a 5.5 mm OD / 2.1 mm ID barrel jack
- 5 V 4 A minimum power supply

Other Raspberry Pi and HUB75 combinations may work, but the installer defaults and timing notes are written for the reference hardware.

## Features

- Browser UI for controlling the panel from a phone, tablet, or computer
- Still image and animated GIF upload with crop, scale, preview, and library save
- Browser pixel-art editor with live matrix preview
- SQLite-backed library with folders, Trash, recovery, permanent delete, and bulk actions
- Slideshow playback with shuffle, interval, transitions, and transition smoothing
- Python Code effects with built-in examples and editable custom effects
- Optional Settings PIN lock with config-file recovery
- Wi-Fi client mode, hotspot mode, and hotspot fallback when saved Wi-Fi is unavailable
- Startup display showing IP address, web port, and countdown
- Matrix timing diagnostics, hardware PWM support, and optional CPU isolation/pinning
- systemd service support for headless appliance use

## Documentation

The detailed manual is in [`docs/wiki/Home.md`](docs/wiki/Home.md).

Key pages:

- [Installation](docs/wiki/installation.md)
- [Hardware and Power](docs/wiki/hardware-power.md)
- [Matrix Timing](docs/wiki/matrix-timing.md)
- [Library](docs/wiki/library.md)
- [Upload](docs/wiki/upload.md)
- [Draw](docs/wiki/draw.md)
- [Code](docs/wiki/code.md)
- [Settings](docs/wiki/settings.md)
- [Wi-Fi and Hotspot](docs/wiki/wifi-hotspot.md)
- [Troubleshooting](docs/wiki/troubleshooting.md)

## Quick install

Start from a Raspberry Pi with Raspberry Pi OS installed and network access working.

```bash
sudo apt update
sudo apt install -y git
cd ~
git clone https://github.com/Charlie22911/Matrix-Art.git
cd Matrix-Art
./scripts/install.sh
sudo reboot
```

The installer asks for:

- Web UI port, default `80`
- Whether the Adafruit GPIO4-to-GPIO18 hardware PWM jumper is installed
- Whether to enable CPU isolation and matrix-thread pinning
- Whether to start Matrix-Art automatically at boot

The generated systemd service uses the folder where `install.sh` was run. For example, an install from `~/Matrix-Art` creates a service that launches Matrix-Art from `~/Matrix-Art`.

After reboot, the panel shows its IP address and web port. Open the web UI from a browser:

```text
http://<panel-ip>/
```

If a non-default port was selected:

```text
http://<panel-ip>:<port>/
```

See [Installation](docs/wiki/installation.md) for ZIP install, copy-from-another-computer install, service modes, driver maintenance, and non-interactive install examples.

## Common commands

Check service status:

```bash
sudo systemctl status matrix-art.service
```

Follow service logs:

```bash
journalctl -u matrix-art.service -f
```

Restart the service:

```bash
sudo systemctl restart matrix-art.service
```

Run manually from the project folder:

```bash
./run.sh
```

Run mock mode without a physical RGB matrix:

```bash
./scripts/run_mock.sh
```

Run matrix timing diagnostics:

```bash
./scripts/check_matrix_timing.sh
```

## Runtime data

Matrix-Art stores runtime data in:

```text
data/matrix_art.sqlite
```

The database stores artwork, frames, drawings, GIF frames, Code effects, folders, settings, Wi-Fi entries, and Settings PIN hashes. Runtime data is ignored by Git.

## Third-party software and license notices

Matrix-Art uses the Raspberry Pi RGB LED matrix driver originally created by Henner Zeller. The LED-matrix library is licensed under the GNU General Public License Version 2.0 or later.

Matrix-Art also references Adafruit's Raspberry Pi RGB Matrix Bonnet documentation and installer workflow for setup of the Adafruit RGB Matrix Bonnet/HAT.

See [`NOTICE`](NOTICE), [`LICENSE`](LICENSE), and [`licenses/GPL-2.0.txt`](licenses/GPL-2.0.txt) for license and attribution details.

## Project origin and use notice

Matrix-Art was created by its maintainer with assistance from ChatGPT by OpenAI. This notice is included for transparency. OpenAI has not reviewed, tested, certified, or endorsed this project.

Matrix-Art is provided as-is under the GNU General Public License version 2. Installing or running it can change Raspberry Pi boot settings, install a systemd service, adjust audio/module loading, configure networking, and drive GPIO-connected LED matrix hardware. Users are responsible for reviewing scripts, wiring hardware correctly, using suitable power equipment, and making backups before installation.

To the fullest extent permitted by applicable law, the author is not responsible for damage, data loss, injury, downtime, or other losses arising from installation, wiring, configuration, operation, modification, or use of this project.
