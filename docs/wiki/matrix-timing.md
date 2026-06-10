# Matrix Timing

HUB75 RGB matrix panels are timing-sensitive. The Raspberry Pi continuously refreshes the panel through GPIO. If Linux scheduling, interrupts, SD card activity, Wi-Fi activity, or power issues disturb refresh timing, the display can flicker or shimmer.

Matrix-Art uses several measures to keep the panel stable, and some configurable values in `config.toml`.

## Hardware PWM path

The reference hardware uses an Adafruit RGB Matrix Bonnet with the quality hardware-pulse path in `config.toml`:

```toml
gpio_mapping = "adafruit-hat-pwm"
hardware_pulse = true
```

This path requires GPIO4 and GPIO18 to be connected on the Bonnet/HAT setup. See:
`https://learn.adafruit.com/adafruit-rgb-matrix-bonnet-for-raspberry-pi/matrix-setup#configure-for-quality-slash-convenience-3201054`.

This improves refresh stability by using the driver’s hardware pulse path. But because this uses PWM timing hardware that is shared with the onboard audio, the onboard Raspberry Pi audio must be off. When you choose hardware PWM during install, Matrix-Art sets `dtparam=audio=off` in the existing Raspberry Pi `config.txt` and writes `/etc/modprobe.d/matrix-art-no-audio.conf` so `snd_bcm2835` stays unloaded.

## GPIO slowdown

```toml
slowdown_gpio = 2
```

`slowdown_gpio` adds small timing delays around GPIO writes. Some HUB75 panels cannot reliably sample the Pi’s fastest GPIO transitions. Slowing the GPIO path slightly can reduce:

- flicker
- sparkles
- row instability
- brightness shimmer
- color noise

Higher values are slower but more forgiving.

## Refresh limit

```toml
limit_refresh_rate_hz = 90
```

A steady 90 Hz refresh can look better than a higher but jittery refresh rate. Refresh limiting helps maintain a consistent cadence under load.

## CPU isolation

On a four-core Pi, Matrix-Art reserves CPU 3 for the timing sensitive matrix refresh thread:

```text
isolcpus=domain,managed_irq,3 nohz_full=3 rcu_nocbs=3 irqaffinity=0,1,2
```

Meaning:

- core 3 is isolated from normal scheduling as much as practical
- periodic scheduler ticks are reduced on core 3
- RCU callback work is moved away from core 3
- normal interrupts are directed to cores 0-2

## Thread affinity

The systemd service allows the process to use all four cores:

```ini
CPUAffinity=0 1 2 3
```

Matrix-Art then splits work internally:

- native matrix refresh thread: CPU 3
- web/app/helper work: CPUs 0-2
- normal Linux IRQs: CPUs 0-2

This prevents the web server, SQLite, GIF processing, uploads, Wi-Fi management, and Code coordination from competing with the matrix refresh thread.

## Realtime priority

The service grants realtime scheduling permission:

```ini
Nice=-10
LimitNICE=-20
LimitRTPRIO=95
```

Matrix-Art briefly enters realtime scheduling while constructing the matrix so the native matrix refresh/PWM thread inherits high-priority timing. The app side is then restored to normal scheduling.

## Checking timing status

Run:

```bash
cd /home/pi/Matrix-Art
./scripts/check_matrix_timing.sh
```

Desired results:

- `isolcpus`, `nohz_full`, `rcu_nocbs`, and `irqaffinity` are present
- service affinity allows `0-3`
- main app/web threads are on `0-2`
- matrix refresh thread is on CPU `3`
- matrix refresh thread is `SCHED_FIFO`
- `snd_bcm2835` is not loaded

## Computational workload note

Heavy package installation or heavy workloads can still cause visible flicker because SD card I/O, memory bandwidth, network activity, power draw, and unavoidable kernel work are shared resources.

Throttling due to undervoltage or exceeding thermal limits can also cause issues due to the inconsistent timing caused by changing CPU clocks speeds. You can check throttle status with the following command:

```bash
vcgencmd get_throttled
```

`throttled=0x0` is the result expected for a system that is not throttling
