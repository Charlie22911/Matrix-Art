# Installation

This page documents the Matrix-Art install flow.

## Reference hardware

- Raspberry Pi Zero 2W
- Adafruit RGB Matrix Bonnet
- 64×64 HUB75 RGB matrix, 3 mm pitch
- 5 V 4 A minimum power supply
- 5.5 mm OD / 2.1 mm ID DC barrel jack power input

## Fresh install

Copy the repository to the Pi, then run:

```bash
cd /home/pi/Matrix-Art
./scripts/install.sh
sudo reboot
```

The installer asks for:

- Web UI port, default `80`
- Whether you are using the Adafruit GPIO4-to-GPIO18 hardware PWM jumper
- Whether to enable CPU isolation and pinning, default yes
- Whether to start Matrix-Art automatically at boot, install the service disabled, or use manual startup only

Dry run:

```bash
./scripts/install.sh --dry-run --yes
```

Recommended non-interactive appliance install:

```bash
./scripts/install.sh --yes
sudo reboot
```

Use port 8080:

```bash
./scripts/install.sh --yes --port 8080
sudo reboot
```

Use convenience wiring without the GPIO4-to-GPIO18 jumper:

```bash
./scripts/install.sh --yes --hardware-pwm no
sudo reboot
```

## What install.sh does

The installer:

- asks for install choices when run interactively
- installs required Debian packages
- creates `.venv/`
- installs Python dependencies
- creates runtime directories under `data/`
- clones latest `hzeller/rpi-rgb-led-matrix` into `vendor/rpi-rgb-led-matrix/`
- builds and installs RGB matrix Python bindings into `.venv/` using a low-parallelism build suitable for small Pi models
- writes Matrix-Art defaults into `config.toml`
- if hardware PWM is selected, sets `dtparam=audio=off` in the existing `config.txt` and writes `/etc/modprobe.d/matrix-art-no-audio.conf` so `snd_bcm2835` stays unloaded
- otherwise leaves `config.txt` alone
- adds or removes CPU-isolation arguments in the existing `cmdline.txt`
- installs, enables, disables, or skips `matrix-art.service` based on your selected startup mode
- enables NetworkManager
- runs Python compile checks
- runs shell syntax checks
- checks that `rgbmatrix` can be imported

The installer backs up boot files before editing the audio or CPU-isolation settings. It also backs up an existing Matrix-Art audio blacklist file before replacing it.

## Service modes

For a dedicated panel appliance, the recommended mode is:

```bash
./scripts/install.sh --yes --service enable
```

For testing before enabling boot startup:

```bash
./scripts/install.sh --yes --service disabled
```

For manual use only:

```bash
./scripts/install.sh --yes --service none
```

Install or refresh only the service file:

```bash
./scripts/install.sh --only-service --service enable --yes
sudo systemctl restart matrix-art.service
```

## Matrix driver maintenance

Install or refresh the latest RGB matrix driver:

```bash
./scripts/install.sh --only-driver --yes
```

Pin a specific upstream commit:

```bash
./scripts/install.sh --only-driver --driver-commit <commit-hash> --yes
```

## Web UI port

The install script asks for the web UI port. It writes that value to:

```toml
[server]
port = 80
```

You can change it later in `config.toml` or from the Settings page.

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

## Mock mode

Mock mode runs without the physical matrix and uses port 8080:

```bash
./scripts/run_mock.sh
```
