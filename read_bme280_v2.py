#!/usr/bin/env python3

import time
from datetime import datetime

import spidev


# ============================================================
# User settings
# ============================================================

SPI_BUS = 0
SPI_CS = 1
SPI_SPEED_HZ = 500_000
SPI_MODE = 0
OUTPUT_HZ = 1.0

DEBUG = False

# ============================================================


def u16_le(data, i):
    return data[i] | (data[i + 1] << 8)


def s16_le(data, i):
    x = u16_le(data, i)
    return x - 65536 if x & 0x8000 else x


def s8(x):
    return x - 256 if x & 0x80 else x


def s12(x):
    return x - 4096 if x & 0x800 else x


class BME280:
    def __init__(self, bus, cs, speed_hz):
        self.spi = spidev.SpiDev()
        self.spi.open(bus, cs)
        self.spi.max_speed_hz = speed_hz
        self.spi.mode = SPI_MODE
        self.spi.bits_per_word = 8

        chip_id = self.read_u8(0xD0)
        print(f"SPI device : /dev/spidev{bus}.{cs}")
        print(f"SPI speed  : {speed_hz} Hz")
        print(f"Chip ID    : 0x{chip_id:02X}")

        if chip_id != 0x60:
            raise RuntimeError(
                f"BME280 not found: expected 0x60, got 0x{chip_id:02X}"
            )

        self.write_u8(0xE0, 0xB6)
        time.sleep(0.010)

        deadline = time.monotonic() + 0.5
        while self.read_u8(0xF3) & 0x01:
            if time.monotonic() > deadline:
                raise TimeoutError("BME280 NVM copy timeout")
            time.sleep(0.002)

        self.read_calibration()

        # Configure while sensor is in sleep mode.
        # config = filter off, spi3w disabled.
        self.write_u8(0xF5, 0x00)

        # Humidity oversampling x1.
        # This becomes effective on the next ctrl_meas write.
        self.write_u8(0xF2, 0x01)

    def close(self):
        self.spi.close()

    def read_regs(self, reg, n):
        # SPI read: RW bit (bit7) = 1.
        # Keep CS low through command + all returned bytes using xfer2().
        rx = self.spi.xfer2([reg | 0x80] + [0xFF] * n)
        return rx[1:]

    def read_u8(self, reg):
        return self.read_regs(reg, 1)[0]

    def write_u8(self, reg, value):
        # SPI write: RW bit (bit7) = 0.
        self.spi.xfer2([reg & 0x7F, value & 0xFF])

    def read_calibration(self):
        c1 = self.read_regs(0x88, 26)
        c2 = self.read_regs(0xE1, 7)

        self.dig_T1 = u16_le(c1, 0)
        self.dig_T2 = s16_le(c1, 2)
        self.dig_T3 = s16_le(c1, 4)

        self.dig_P1 = u16_le(c1, 6)
        self.dig_P2 = s16_le(c1, 8)
        self.dig_P3 = s16_le(c1, 10)
        self.dig_P4 = s16_le(c1, 12)
        self.dig_P5 = s16_le(c1, 14)
        self.dig_P6 = s16_le(c1, 16)
        self.dig_P7 = s16_le(c1, 18)
        self.dig_P8 = s16_le(c1, 20)
        self.dig_P9 = s16_le(c1, 22)

        self.dig_H1 = c1[25]
        self.dig_H2 = s16_le(c2, 0)
        self.dig_H3 = c2[2]
        self.dig_H4 = s12((c2[3] << 4) | (c2[4] & 0x0F))
        self.dig_H5 = s12((c2[5] << 4) | (c2[4] >> 4))
        self.dig_H6 = s8(c2[6])

        if DEBUG:
            print("Calibration:")
            for name in (
                "dig_T1", "dig_T2", "dig_T3",
                "dig_P1", "dig_P2", "dig_P3", "dig_P4", "dig_P5",
                "dig_P6", "dig_P7", "dig_P8", "dig_P9",
                "dig_H1", "dig_H2", "dig_H3", "dig_H4", "dig_H5", "dig_H6",
            ):
                print(f"  {name} = {getattr(self, name)}")

    def perform_forced_measurement(self):
        # osrs_t = x1 (001)
        # osrs_p = x1 (001)
        # mode   = forced (01)
        # 0b00100101 = 0x25
        self.write_u8(0xF4, 0x25)

        # Bosch maximum measurement time for x1/x1/x1 is about 9.3 ms.
        # Wait 20 ms to avoid racing the measuring flag immediately after
        # entering forced mode.
        time.sleep(0.020)

        # If still measuring, wait until it really finishes.
        deadline = time.monotonic() + 0.5
        while self.read_u8(0xF3) & 0x08:
            if time.monotonic() > deadline:
                raise TimeoutError("BME280 measurement timeout")
            time.sleep(0.002)

    def read_raw(self):
        self.perform_forced_measurement()

        data = self.read_regs(0xF7, 8)

        adc_p = (
            (data[0] << 12)
            | (data[1] << 4)
            | (data[2] >> 4)
        )

        adc_t = (
            (data[3] << 12)
            | (data[4] << 4)
            | (data[5] >> 4)
        )

        adc_h = (
            (data[6] << 8)
            | data[7]
        )

        if DEBUG:
            print(
                f"RAW P={adc_p} T={adc_t} H={adc_h} "
                f"bytes={' '.join(f'{x:02X}' for x in data)}"
            )

        return adc_t, adc_p, adc_h

    # Bosch datasheet Appendix A: double precision compensation formulas.
    def compensate_temperature(self, adc_t):
        var1 = (
            adc_t / 16384.0
            - self.dig_T1 / 1024.0
        ) * self.dig_T2

        var2 = (
            adc_t / 131072.0
            - self.dig_T1 / 8192.0
        )
        var2 = var2 * var2 * self.dig_T3

        # Datasheet carries t_fine as a signed 32-bit integer.
        self.t_fine = int(var1 + var2)

        return (var1 + var2) / 5120.0

    def compensate_pressure(self, adc_p):
        var1 = self.t_fine / 2.0 - 64000.0
        var2 = var1 * var1 * self.dig_P6 / 32768.0
        var2 += var1 * self.dig_P5 * 2.0
        var2 = var2 / 4.0 + self.dig_P4 * 65536.0
        var1 = (
            self.dig_P3 * var1 * var1 / 524288.0
            + self.dig_P2 * var1
        ) / 524288.0
        var1 = (1.0 + var1 / 32768.0) * self.dig_P1

        if var1 == 0.0:
            raise RuntimeError("Invalid pressure calibration")

        p = 1048576.0 - adc_p
        p = (p - var2 / 4096.0) * 6250.0 / var1
        var1 = self.dig_P9 * p * p / 2147483648.0
        var2 = p * self.dig_P8 / 32768.0
        p = p + (var1 + var2 + self.dig_P7) / 16.0

        # p is Pa
        return p / 100.0

    def compensate_humidity(self, adc_h):
        var_h = self.t_fine - 76800.0

        var_h = (
            adc_h
            - (
                self.dig_H4 * 64.0
                + self.dig_H5 / 16384.0 * var_h
            )
        ) * (
            self.dig_H2 / 65536.0
            * (
                1.0
                + self.dig_H6 / 67108864.0
                * var_h
                * (
                    1.0
                    + self.dig_H3 / 67108864.0 * var_h
                )
            )
        )

        var_h = var_h * (
            1.0 - self.dig_H1 * var_h / 524288.0
        )

        return max(0.0, min(100.0, var_h))

    def read_environment(self):
        adc_t, adc_p, adc_h = self.read_raw()

        temperature = self.compensate_temperature(adc_t)
        pressure = self.compensate_pressure(adc_p)
        humidity = self.compensate_humidity(adc_h)

        return temperature, pressure, humidity


def main():
    sensor = BME280(SPI_BUS, SPI_CS, SPI_SPEED_HZ)

    period = 1.0 / OUTPUT_HZ
    next_time = time.monotonic()

    print()
    print(
        "time,"
        "temperature_degC,"
        "pressure_hPa,"
        "humidity_percent"
    )

    try:
        while True:
            if time.monotonic() < next_time:
                time.sleep(next_time - time.monotonic())

            temperature, pressure, humidity = sensor.read_environment()

            timestamp = datetime.now().strftime("%Y-%m%d-%H:%M:%S")

            print(
                f"{timestamp},"
                f"{temperature:.2f},"
                f"{pressure:.2f},"
                f"{humidity:.2f}",
                flush=True,
            )

            if not (-40.0 <= temperature <= 85.0):
                print(
                    f"WARNING: temperature out of BME280 operating range: "
                    f"{temperature:.2f} degC"
                )

            if not (300.0 <= pressure <= 1100.0):
                print(
                    f"WARNING: pressure out of BME280 operating range: "
                    f"{pressure:.2f} hPa"
                )

            if not (0.0 <= humidity <= 100.0):
                print(
                    f"WARNING: humidity out of range: {humidity:.2f} %"
                )

            next_time += period

    except KeyboardInterrupt:
        print()
    finally:
        sensor.close()


if __name__ == "__main__":
    main()
