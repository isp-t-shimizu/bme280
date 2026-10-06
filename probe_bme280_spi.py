#!/usr/bin/env python3

import spidev

SPI_BUS = 0
SPI_CS = 1

TESTS = [
    (0, 100_000),
    (0, 500_000),
    (3, 100_000),
    (3, 500_000),
]


def read_u8(spi, reg):
    rx = spi.xfer2([reg | 0x80, 0xFF])
    return rx[1]


def main():
    for mode, speed in TESTS:
        spi = spidev.SpiDev()
        spi.open(SPI_BUS, SPI_CS)
        spi.mode = mode
        spi.max_speed_hz = speed
        spi.bits_per_word = 8

        try:
            print("=" * 72)
            print(f"/dev/spidev{SPI_BUS}.{SPI_CS}, mode={mode}, speed={speed} Hz")

            fixed_regs = [
                ("ID",        0xD0),
                ("reset",     0xE0),
                ("ctrl_hum",  0xF2),
                ("status",    0xF3),
                ("ctrl_meas", 0xF4),
                ("config",    0xF5),
            ]

            print("\nKnown/control registers:")
            for name, reg in fixed_regs:
                value = read_u8(spi, reg)
                print(f"  {name:9s} 0x{reg:02X} = 0x{value:02X}")

            print("\nCalibration registers, individual reads:")
            values = []
            for reg in range(0x88, 0xA2):
                value = read_u8(spi, reg)
                values.append(value)
                print(f"  0x{reg:02X} = 0x{value:02X}")

            print("\nCalibration bytes:")
            print("  " + " ".join(f"{x:02X}" for x in values))

            hum_cal = [read_u8(spi, reg) for reg in range(0xE1, 0xE8)]
            print("\nHumidity calibration 0xE1..0xE7:")
            print("  " + " ".join(f"{x:02X}" for x in hum_cal))

            raw = [read_u8(spi, reg) for reg in range(0xF7, 0xFF)]
            print("\nMeasurement registers 0xF7..0xFE:")
            print("  " + " ".join(f"{x:02X}" for x in raw))

        finally:
            spi.close()

        print()


if __name__ == "__main__":
    main()
