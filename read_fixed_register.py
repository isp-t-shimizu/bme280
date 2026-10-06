
# A]pi@raspberrypi:~ $ ls -l /dev/spidev*
# crw-rw---- 1 root spi 153, 0 12月 26 04:34 /dev/spidev0.1
#
# curl -LsSf https://astral.sh/uv/install.sh | sh
# 
#A]pi@raspberrypi:~/work/bme280 $ curl -LsSf https://astral.sh/uv/install.sh | sh
# downloading uv 0.12.23 armv7-unknown-linux-gnueabihf
# installing to /home/pi/.local/bin
#    uv
#    uvx
#    everything's installed!
#
# To add $HOME/.local/bin to your PATH, either restart your shell or run:
#
#    source $HOME/.local/bin/env (sh, bash, zsh)
#    source $HOME/.local/bin/env.fish (fish)
# A]pi@raspberrypi:~/work/bme280 $ fg
# emacs -nw read_fixed_register.py
#
#[1]+  停止                  emacs -nw read_fixed_register.py
# A]pi@raspberrypi:~/work/bme280 $ source ~/.profile
# A]pi@raspberrypi:~/work/bme280 $ uv --version
# uv 0.12.23 (armv7-unknown-linux-gnueabihf)
# A]pi@raspberrypi:~/work/bme280 $ ~/.local/bin/uv --version
# uv 0.12.23 (armv7-unknown-linux-gnueabihf)
# A]pi@raspberrypi:~/work/bme280 $ uname -m
# armv7l
# A]pi@raspberrypi:~/work/bme280 $ ldd --version | head -1
# ldd (Debian GLIBC 2.24-11+deb9u3) 2.24
# A]pi@raspberrypi:~/work/bme280 $ uv python install 3.14
# Installed Python 3.14.8 in 12.20s
#  + cpython-3.14.8-linux-armv7-gnueabihf (python3.14)
#
# A]pi@raspberrypi:~/work/bme280 $ uv run --python 3.14 python --version
# Python 3.14.8
# A]pi@raspberrypi:~/work/bme280 $ uv venv --python 3.14 .venv
# Using CPython 3.14.8
# Creating virtual environment at: .venv
# Activate with: source .venv/bin/activate
# A]pi@raspberrypi:~/work/bme280 $ source .venv/bin/activate
# (.venv) A]pi@raspberrypi:~/work/bme280 $ python --version
# Python 3.14.8
# (.venv) A]pi@raspberrypi:~/work/bme280 $ uv pip install spidev
#  Resolved 1 package in 1.24s
#        Built spidev==3.8                                                                                                                #    Prepared 1 package in 23.66s
#        Installed 1 package in 5ms
#         + spidev==3.8
#(.venv) A]pi@raspberrypi:~/work/bme280 $ python ./read_fixed_register.py
#TX: ['0xFF', '0x60']
#RX: ['0xFF', '0x60']
#Chip ID = 0x60

import spidev

# =========================
# User settings
# =========================
SPI_BUS = 0
SPI_CS = 1
SPI_SPEED_HZ = 500_000
SPI_MODE = 0
# =========================

spi = spidev.SpiDev()

try:
    spi.open(SPI_BUS, SPI_CS)

    spi.max_speed_hz = SPI_SPEED_HZ
    spi.mode = SPI_MODE
    spi.bits_per_word = 8
    
    # BME280 Chip ID register = 0xD0
    #
    # BME280 SPI read:
    # bit7 = 1
    #
    # 0xD0 already has bit7 = 1
    tx = [0xD0, 0x00]
    
    rx = spi.xfer2(tx)
    
    print("TX:", [f"0x{x:02X}" for x in tx])
    print("RX:", [f"0x{x:02X}" for x in rx])
    print(f"Chip ID = 0x{rx[1]:02X}")
    
finally:
    spi.close()



