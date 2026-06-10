# Hardware and Power

Matrix-Art is designed around a specific RGB matrix appliance build.

## Reference hardware

- Raspberry Pi Zero 2W
- Adafruit RGB Matrix Bonnet
- 64×64 HUB75 RGB LED matrix panel
- 3 mm panel pitch
- 5 V DC input through a 5.5 mm OD / 2.1 mm ID barrel jack
- 5 V 4 A minimum supply

## Power notes

RGB matrix panels can draw large current depending on brightness and content. Use a stable 5 V supply rated for at least 4 A.

Symptoms of weak or unstable power can include:

- display flicker
- random sparkles
- panel resets
- Raspberry Pi undervoltage warnings
- Wi-Fi instability
- spontaneous reboot

Check throttling/undervoltage status:

```bash
vcgencmd get_throttled
```

Ideal result:

```text
throttled=0x0
```

## Matrix Bonnet notes

Matrix-Art supports the Adafruit Bonnet quality hardware-PWM path:

```toml
gpio_mapping = "adafruit-hat-pwm"
hardware_pulse = true
```

That path uses PWM timing hardware and conflicts with onboard audio. When you select hardware PWM during install, the installer turns onboard audio off with `dtparam=audio=off` in the existing Raspberry Pi `config.txt` and keeps `snd_bcm2835` from loading.

## Panel settings

Reference defaults:

```toml
[panel]
rows = 64
cols = 64
chain_length = 1
parallel = 1
gpio_mapping = "adafruit-hat-pwm"
slowdown_gpio = 2
limit_refresh_rate_hz = 90
```

Adjust `slowdown_gpio` or `limit_refresh_rate_hz` in `config.toml` if your specific panel behaves differently.
