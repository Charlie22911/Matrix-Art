# Installation

This page covers installing Matrix-Art on Raspberry Pi OS and explains the main installer choices.

## Reference hardware

- Raspberry Pi Zero 2W
- Adafruit RGB Matrix Bonnet
- 64×64 HUB75 RGB matrix, 3 mm pitch
- 5 V 4 A minimum power supply
- 5.5 mm OD / 2.1 mm ID DC barrel jack power input

## Fresh install

Start from a Raspberry Pi with Raspberry Pi OS installed, network access working, and a terminal open on the Pi. SSH works fine.

Choose one of these methods to place Matrix-Art on the Pi.

### Option A: clone from GitHub on the Pi

This is the recommended path when the Pi has internet access.

```bash
sudo apt update
sudo apt install -y git
cd ~
git clone https://github.com/Charlie22911/Matrix-Art.git
cd Matrix-Art
```

### Option B: download the ZIP on the Pi

This creates a plain source copy without Git history.

```bash
sudo apt update
sudo apt install -y curl unzip
cd ~
rm -rf Matrix-Art Matrix-Art-main Matrix-Art.zip
curl -L -o Matrix-Art.zip https://github.com/Charlie22911/Matrix-Art/archive/refs/heads/main.zip
unzip Matrix-Art.zip
mv Matrix-Art-main Matrix-Art
cd Matrix-Art
```

### Option C: copy from another computer

Run this command on the computer that already has the Matrix-Art folder. Replace `<pi-ip>` with the Pi's IP address and replace `pi` if the Pi uses a different username.

```bash
rsync -a --delete --exclude='.git/' ./Matrix-Art/ pi@<pi-ip>:~/Matrix-Art/
```

Then log in to the Pi and enter the project folder.

```bash
ssh pi@<pi-ip>
cd ~/Matrix-Art
```

## Run the installer

From the Matrix-Art project folder:

```bash
chmod +x ./scripts/*.sh
./scripts/install.sh
sudo reboot
```

The installer asks for:

- Web UI port, default `80`
- Whether the Adafruit GPIO4-to-GPIO18 hardware PWM jumper is installed
- Whether to enable CPU isolation and pinning, default yes
- Whether to start Matrix-Art automatically at boot, install the service disabled, or use manual startup only

The generated service uses the folder where `install.sh` was run. An install from `~/Matrix-Art` creates a service that launches Matrix-Art from `~/Matrix-Art`.

After reboot, the panel shows the IP address, web port, and startup countdown. Open the web UI from a browser:

```text
http://<panel-ip>/
```

For a non-default port:

```text
http://<panel-ip>:<port>/
```

## Non-interactive install examples

Dry run:

```bash
./scripts/install.sh --dry-run --yes
```

Recommended appliance install:

```bash
./scripts/install.sh --yes
sudo reboot
```

Use port 8080:

```bash
./scripts/install.sh --yes --port 8080
sudo reboot
```

Use convenience wiring without the GPIO4-to-GPIO18 hardware PWM jumper:

```bash
./scripts/install.sh --yes --hardware-pwm no
sudo reboot
```

Disable CPU isolation and pinning:

```bash
./scripts/install.sh --yes --isolation no
sudo reboot
```

## What install.sh does

The installer:

- asks for install choices when run interactively
- makes Matrix-Art shell scripts executable
- installs required Debian packages
- creates `.venv/`
- installs Python dependencies
- creates runtime directories under `data/`
- clones the latest `hzeller/rpi-rgb-led-matrix` source into `vendor/rpi-rgb-led-matrix/`
- builds and installs RGB matrix Python bindings into `.venv/` using a low-parallelism build suitable for small Pi models
- writes Matrix-Art defaults into `config.toml`
- if hardware PWM is selected, sets `dtparam=audio=off` in the existing `config.txt` and writes `/etc/modprobe.d/matrix-art-no-audio.conf` so `snd_bcm2835` stays unloaded
- otherwise leaves `config.txt` alone
- adds or removes Matrix-Art CPU-isolation arguments in the existing `cmdline.txt`
- asks before replacing unrelated existing CPU-isolation arguments
- installs, enables, disables, or skips `matrix-art.service` based on the selected startup mode
- enables NetworkManager
- runs Python compile checks
- runs shell syntax checks
- checks that `rgbmatrix` can be imported

The installer backs up boot files before editing audio or CPU-isolation settings. It also backs up an existing Matrix-Art audio blacklist file before replacing it.

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

If the project folder is moved later, run the service-refresh command again from the new project folder.

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

The install script writes the selected web UI port to:

```toml
[server]
port = 80
```

The port can be changed later in `config.toml` or from the Settings page.

## Normal service commands

```bash
sudo systemctl status matrix-art.service
sudo systemctl restart matrix-art.service
sudo systemctl stop matrix-art.service
journalctl -u matrix-art.service -f
```

## Manual run

```bash
cd ~/Matrix-Art
./run.sh
```

## Mock mode

Mock mode runs without the physical matrix and uses port 8080:

```bash
./scripts/run_mock.sh
```
