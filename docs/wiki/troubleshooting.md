# Troubleshooting

## Cannot open the web UI

Check service status:

```bash
sudo systemctl status matrix-art.service
```

Follow logs:

```bash
journalctl -u matrix-art.service -f
```

Check the IP address and port shown on the panel at startup. If saved Wi-Fi is unavailable, Matrix-Art may start hotspot mode.

## Port 80 needs root

Matrix-Art runs as a service on port 80 by default. To install or refresh the service:

```bash
./scripts/install.sh --only-service --service enable --yes
sudo systemctl restart matrix-art.service
```

Matrix-Art can also be installed on a high port, such as 8080:

```bash
./scripts/install.sh --yes --port 8080
```

Mock mode uses port 8080.

## Display issues

For issues with display flicker, check:

```bash
./scripts/check_matrix_timing.sh
vcgencmd get_throttled
```

Recommended reference timing:

```toml
slowdown_gpio = 2
limit_refresh_rate_hz = 90
gpio_mapping = "adafruit-hat-pwm"
hardware_pulse = true
```

Make sure `snd_bcm2835` is not loaded. If hardware PWM was selected during install, Matrix-Art writes `/etc/modprobe.d/matrix-art-no-audio.conf` so the module stays unloaded after reboot.

Adafruit's RGB Matrix Bonnet guide is available at `https://learn.adafruit.com/adafruit-rgb-matrix-bonnet-for-raspberry-pi/overview`.

## Settings PIN forgotten

Edit `config.toml`:

```toml
[security]
reset_settings_pin = true
```

Restart:

```bash
sudo systemctl restart matrix-art.service
```

Open Settings and set a new PIN.

## Code effect does not show a useful thumbnail

Run the Code item until the panel displays a useful frame, then click:

```text
Use Current Display as Thumbnail
```
