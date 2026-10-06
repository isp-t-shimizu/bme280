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

# ============================================================


REG_ID = 0xD0
REG_RESET = 0xE0
REG_CTRL_HUM = 0xF2
REG_STATUS = 0xF3
REG_CTRL_MEAS = 0xF4
REG_CONFIG = 0xF5
REG_DATA = 0xF7

BME280_CHIP_ID = 0x60


def u16_le(data, offset):
    return data[offset] | (data[offset + 1] << 8)


def s16_le(data, offset):
    value = u16_le(data, offset)
    if value & 0x8000:
        value -= 0x10000
    return value


def s8(value):
    if value & 0x80:
        value -= 0x100
    return value


def s12(value):
    if value & 0x800:
        value -= 0x1000
    return value


class BME280:
    def __init__(self, bus, cs, speed_hz):
        self.spi = spidev.SpiDev()
        self.spi.open(bus, cs)

        self.spi.max_speed_hz = speed_hz
        self.spi.mode = SPI_MODE
        self.spi.bits_per_word = 8

        chip_id = self.read_u8(REG_ID)

        print(f"SPI device : /dev/spidev{bus}.{cs}")
        print(f"SPI speed  : {speed_hz} Hz")
        print(f"Chip ID    : 0x{chip_id:02X}")

        if chip_id != BME280_CHIP_ID:
            raise RuntimeError(
                f"BME280 not found: expected 0x60, got 0x{chip_id:02X}"
            )

        # Soft reset
        self.write_u8(REG_RESET, 0xB6)

        time.sleep(0.01)

        # Wait for calibration data copy to finish
        timeout = time.monotonic() + 0.5

        while self.read_u8(REG_STATUS) & 0x01:
            if time.monotonic() > timeout:
                raise TimeoutError("BME280 NVM copy timeout")
            time.sleep(0.002)

        self.read_calibration()

        # Humidity oversampling x1
        self.write_u8(REG_CTRL_HUM, 0x01)

        # filter off
        # 4-wire SPI
        self.write_u8(REG_CONFIG, 0x00)

    def close(self):
        self.spi.close()

    def read_registers(self, reg, length):
        # BME280 SPI read:
        # bit7 = 1
        tx = [reg | 0x80] + [0x00] * length
        rx = self.spi.xfer2(tx)

        # First byte is dummy/command phase
        return rx[1:]

    def read_u8(self, reg):
        return self.read_registers(reg, 1)[0]

    def write_u8(self, reg, value):
        # BME280 SPI write:
        # bit7 = 0
        self.spi.xfer2([
            reg & 0x7F,
            value & 0xFF,
        ])

    def read_calibration(self):
        calib1 = self.read_registers(0x88, 26)
        calib2 = self.read_registers(0xE1, 7)

        self.dig_T1 = u16_le(calib1, 0)
        self.dig_T2 = s16_le(calib1, 2)
        self.dig_T3 = s16_le(calib1, 4)

        self.dig_P1 = u16_le(calib1, 6)
        self.dig_P2 = s16_le(calib1, 8)
        self.dig_P3 = s16_le(calib1, 10)
        self.dig_P4 = s16_le(calib1, 12)
        self.dig_P5 = s16_le(calib1, 14)
        self.dig_P6 = s16_le(calib1, 16)
        self.dig_P7 = s16_le(calib1, 18)
        self.dig_P8 = s16_le(calib1, 20)
        self.dig_P9 = s16_le(calib1, 22)

        self.dig_H1 = calib1[25]

        self.dig_H2 = s16_le(calib2, 0)
        self.dig_H3 = calib2[2]

        self.dig_H4 = s12(
            (calib2[3] << 4)
            | (calib2[4] & 0x0F)
        )

        self.dig_H5 = s12(
            (calib2[5] << 4)
            | (calib2[4] >> 4)
        )

        self.dig_H6 = s8(calib2[6])

    def trigger_measurement(self):
        # Temperature oversampling x1
        # Pressure oversampling x1
        # Forced mode
        #
        # osrs_t = 001
        # osrs_p = 001
        # mode   = 01
        #
        # => 0b00100101 = 0x25
        self.write_u8(REG_CTRL_MEAS, 0x25)

        timeout = time.monotonic() + 0.5

        # Wait while measuring bit is set
        while self.read_u8(REG_STATUS) & 0x08:
            if time.monotonic() > timeout:
                raise TimeoutError("BME280 measurement timeout")
            time.sleep(0.002)

    def read_raw(self):
        self.trigger_measurement()

        data = self.read_registers(REG_DATA, 8)

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

        return adc_t, adc_p, adc_h

    def compensate_temperature(self, adc_t):
        var1 = (
            ((adc_t >> 3) - (self.dig_T1 << 1))
            * self.dig_T2
        ) >> 11

        var2 = (
            (
                (
                    ((adc_t >> 4) - self.dig_T1)
                    * ((adc_t >> 4) - self.dig_T1)
                ) >> 12
            )
            * self.dig_T3
        ) >> 14

        self.t_fine = var1 + var2

        temperature_001c = (
            self.t_fine * 5 + 128
        ) >> 8

        return temperature_001c / 100.0

    def compensate_pressure(self, adc_p):
        var1 = self.t_fine - 128000

        var2 = var1 * var1 * self.dig_P6
        var2 += (var1 * self.dig_P5) << 17
        var2 += self.dig_P4 << 35

        var1 = (
            (var1 * var1 * self.dig_P3) >> 8
        ) + (
            (var1 * self.dig_P2) << 12
        )

        var1 = (
            ((1 << 47) + var1)
            * self.dig_P1
        ) >> 33

        if var1 == 0:
            raise RuntimeError("Invalid pressure calibration")

        pressure = 1048576 - adc_p

        pressure = (
            ((pressure << 31) - var2)
            * 3125
        ) // var1

        var1 = (
            self.dig_P9
            * (pressure >> 13)
            * (pressure >> 13)
        ) >> 25

        var2 = (
            self.dig_P8
            * pressure
        ) >> 19

        pressure = (
            (pressure + var1 + var2) >> 8
        ) + (
            self.dig_P7 << 4
        )

        # Bosch result is Q24.8 Pa
        pressure_pa = pressure / 256.0

        return pressure_pa / 100.0

    def compensate_humidity(self, adc_h):
        v = self.t_fine - 76800

        v = (
            (
                (
                    (
                        adc_h << 14
                    )
                    - (
                        self.dig_H4 << 20
                    )
                    - (
                        self.dig_H5 * v
                    )
                    + 16384
                ) >> 15
            )
            *
            (
                (
                    (
                        (
                            (
                                (
                                    v * self.dig_H6
                                ) >> 10
                            )
                            *
                            (
                                (
                                    (
                                        v
                                        * self.dig_H3
                                    ) >> 11
                                )
                                + 32768
                            )
                        ) >> 10
                    )
                    + 2097152
                )
                * self.dig_H2
                + 8192
            ) >> 14
        )

        v = v - (
            (
                (
                    (
                        (v >> 15)
                        * (v >> 15)
                    ) >> 7
                )
                * self.dig_H1
            ) >> 4
        )

        v = max(v, 0)
        v = min(v, 419430400)

        humidity = (v >> 12) / 1024.0

        return humidity

    def read_environment(self):
        adc_t, adc_p, adc_h = self.read_raw()

        # Temperature must be compensated first because
        # t_fine is used by pressure and humidity compensation.
        temperature = self.compensate_temperature(adc_t)
        pressure = self.compensate_pressure(adc_p)
        humidity = self.compensate_humidity(adc_h)

        return temperature, pressure, humidity


def main():
    sensor = BME280(
        SPI_BUS,
        SPI_CS,
        SPI_SPEED_HZ,
    )

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
            now = time.monotonic()

            if now < next_time:
                time.sleep(next_time - now)

            temperature, pressure, humidity = (
                sensor.read_environment()
            )

            timestamp = datetime.now().strftime(
                "%Y-%m%d-%H:%M:%S"
            )

            print(
                f"{timestamp},"
                f"{temperature:.2f},"
                f"{pressure:.2f},"
                f"{humidity:.2f}",
                flush=True,
            )

            next_time += period

    except KeyboardInterrupt:
        print()

    finally:
        sensor.close()


if __name__ == "__main__":
    main()
