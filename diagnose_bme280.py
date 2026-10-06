#!/usr/bin/env python3

import time
import spidev

SPI_BUS = 0
SPI_CS = 1
SPI_SPEED_HZ = 500_000
SPI_MODE = 0


def hex_bytes(data):
    return " ".join(f"{x:02X}" for x in data)


def s8(x):
    return x - 256 if x & 0x80 else x


def u16_le(data, i):
    return data[i] | (data[i + 1] << 8)


def s16_le(data, i):
    x = u16_le(data, i)
    return x - 65536 if x & 0x8000 else x


def s12(x):
    return x - 4096 if x & 0x800 else x


spi = spidev.SpiDev()
spi.open(SPI_BUS, SPI_CS)
spi.max_speed_hz = SPI_SPEED_HZ
spi.mode = SPI_MODE
spi.bits_per_word = 8


def read_regs(reg, n):
    rx = spi.xfer2([reg | 0x80] + [0xFF] * n)
    return rx[1:]


def read_u8(reg):
    return read_regs(reg, 1)[0]


def write_u8(reg, value):
    spi.xfer2([reg & 0x7F, value & 0xFF])


try:
    print(f"SPI: /dev/spidev{SPI_BUS}.{SPI_CS}, {SPI_SPEED_HZ} Hz, mode {SPI_MODE}")

    chip_id = read_u8(0xD0)
    print(f"Chip ID: 0x{chip_id:02X}")
    if chip_id != 0x60:
        raise RuntimeError("Chip ID is not 0x60")

    # Soft reset
    write_u8(0xE0, 0xB6)
    time.sleep(0.010)

    # Wait for NVM copy to finish
    deadline = time.monotonic() + 0.5
    while read_u8(0xF3) & 0x01:
        if time.monotonic() > deadline:
            raise TimeoutError("NVM copy timeout")
        time.sleep(0.002)

    # Calibration data, burst read
    c1 = read_regs(0x88, 26)
    c2 = read_regs(0xE1, 7)

    # Calibration data, one register at a time
    c1_single = [read_u8(0x88 + i) for i in range(26)]
    c2_single = [read_u8(0xE1 + i) for i in range(7)]

    print("\nCalibration raw:")
    print("0x88..0xA1 burst :", hex_bytes(c1))
    print("0x88..0xA1 single:", hex_bytes(c1_single))
    print("match:", c1 == c1_single)

    print("0xE1..0xE7 burst :", hex_bytes(c2))
    print("0xE1..0xE7 single:", hex_bytes(c2_single))
    print("match:", c2 == c2_single)

    dig_T1 = u16_le(c1, 0)
    dig_T2 = s16_le(c1, 2)
    dig_T3 = s16_le(c1, 4)

    dig_P1 = u16_le(c1, 6)
    dig_P2 = s16_le(c1, 8)
    dig_P3 = s16_le(c1, 10)
    dig_P4 = s16_le(c1, 12)
    dig_P5 = s16_le(c1, 14)
    dig_P6 = s16_le(c1, 16)
    dig_P7 = s16_le(c1, 18)
    dig_P8 = s16_le(c1, 20)
    dig_P9 = s16_le(c1, 22)

    dig_H1 = c1[25]
    dig_H2 = s16_le(c2, 0)
    dig_H3 = c2[2]
    dig_H4 = s12((c2[3] << 4) | (c2[4] & 0x0F))
    dig_H5 = s12((c2[5] << 4) | (c2[4] >> 4))
    dig_H6 = s8(c2[6])

    print("\nCalibration coefficients:")
    for name, value in [
        ("dig_T1", dig_T1), ("dig_T2", dig_T2), ("dig_T3", dig_T3),
        ("dig_P1", dig_P1), ("dig_P2", dig_P2), ("dig_P3", dig_P3),
        ("dig_P4", dig_P4), ("dig_P5", dig_P5), ("dig_P6", dig_P6),
        ("dig_P7", dig_P7), ("dig_P8", dig_P8), ("dig_P9", dig_P9),
        ("dig_H1", dig_H1), ("dig_H2", dig_H2), ("dig_H3", dig_H3),
        ("dig_H4", dig_H4), ("dig_H5", dig_H5), ("dig_H6", dig_H6),
    ]:
        print(f"{name:7s} = {value}")

    # Configure while in sleep mode:
    # config: filter off, 3-wire SPI off
    write_u8(0xF5, 0x00)
    # humidity oversampling x1
    write_u8(0xF2, 0x01)
    # temp x1, pressure x1, forced mode
    write_u8(0xF4, 0x25)

    # x1/x1/x1 takes <= about 9.3 ms; wait safely longer.
    time.sleep(0.020)

    status = read_u8(0xF3)
    ctrl_hum = read_u8(0xF2)
    ctrl_meas = read_u8(0xF4)
    config = read_u8(0xF5)

    print("\nControl registers after conversion:")
    print(f"status    = 0x{status:02X}")
    print(f"ctrl_hum  = 0x{ctrl_hum:02X}")
    print(f"ctrl_meas = 0x{ctrl_meas:02X}")
    print(f"config    = 0x{config:02X}")

    data = read_regs(0xF7, 8)

    adc_p = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
    adc_t = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)
    adc_h = (data[6] << 8) | data[7]

    print("\nMeasurement raw:")
    print("0xF7..0xFE:", hex_bytes(data))
    print(f"adc_P = {adc_p} (0x{adc_p:05X})")
    print(f"adc_T = {adc_t} (0x{adc_t:05X})")
    print(f"adc_H = {adc_h} (0x{adc_h:04X})")

finally:
    spi.close()
