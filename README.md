# BME280 SPI Test on Raspberry Pi

Raspberry Pi から SPI 接続した BME280 の動作確認を行うための環境構築・テスト手順です。

この環境では、古い Raspbian Stretch の system Python (`Python 3.5.3`) は変更せず、
`uv` を使って Python 3.14.8 の仮想環境を追加しています。

## 1. Tested environment

動作確認した環境:

```text
OS      : Raspbian GNU/Linux 9 (stretch)
Kernel  : Linux 4.14.79-v7+
Arch    : armv7l
glibc   : 2.24
uv      : 0.12.23
Python  : 3.14.8
spidev  : 3.8
```

system Python はそのまま残しています。

```bash
/usr/bin/python3 --version
# Python 3.5.3
```

BME280 用には `uv` で導入した Python 3.14.8 を使用します。

---

## 2. BME280 SPI connection

使用ボード:

- Switch Science BME280 breakout board
- 4-wire SPI

現在の Raspberry Pi では以下のデバイスが確認されています。

```bash
ls -l /dev/spidev*
```

確認結果:

```text
crw-rw---- 1 root spi 153, 0 ... /dev/spidev0.1
```

`/dev/spidev0.1` は、

```text
bus = 0
chip select = 1
```

を意味します。

Python では以下の設定を使用します。

```python
SPI_BUS = 0
SPI_CS = 1
SPI_SPEED_HZ = 500_000
SPI_MODE = 0
```

Raspberry Pi の SPI0 CE1 を使用する場合の接続例:

| Function | Raspberry Pi | BME280 |
|---|---|---|
| 3.3 V | Pin 1 | Vcore |
| GND | Pin 6 | GND |
| MOSI | Pin 19 / GPIO10 | SDI |
| MISO | Pin 21 / GPIO9 | SDO |
| SCLK | Pin 23 / GPIO11 | SCK |
| CS | Pin 26 / GPIO7 / CE1 | CSB |

> `/dev/spidev0.0` を使用する場合は CE0 (Pin 24 / GPIO8) を使用し、
> `SPI_CS = 0` に変更します。

---

## 3. Install uv

`uv` をインストールします。

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

実際のインストール結果:

```text
downloading uv 0.12.23 armv7-unknown-linux-gnueabihf
installing to /home/pi/.local/bin
  uv
  uvx
everything's installed!
```

PATH を反映します。

```bash
source $HOME/.local/bin/env
```

または shell を再起動します。

確認:

```bash
uv --version
```

動作確認時:

```text
uv 0.12.23 (armv7-unknown-linux-gnueabihf)
```

---

## 4. Check architecture and glibc

```bash
uname -m
```

確認結果:

```text
armv7l
```

glibc:

```bash
ldd --version | head -1
```

確認結果:

```text
ldd (Debian GLIBC 2.24-11+deb9u3) 2.24
```

---

## 5. Install Python 3.14 with uv

Python 3.14 をインストールします。

```bash
uv python install 3.14
```

動作確認時:

```text
Installed Python 3.14.8
 + cpython-3.14.8-linux-armv7-gnueabihf (python3.14)
```

確認:

```bash
uv run --python 3.14 python --version
```

```text
Python 3.14.8
```

---

## 6. Create virtual environment

プロジェクトディレクトリへ移動します。

```bash
cd ~/work/bme280
```

Python 3.14 を使用して `.venv` を作成します。

```bash
uv venv --python 3.14 .venv
```

有効化:

```bash
source .venv/bin/activate
```

確認:

```bash
python --version
```

```text
Python 3.14.8
```

---

## 7. Install dependencies

このプロジェクトでは `requirements.txt` に依存パッケージを記録しています。

```text
spidev==3.8
```

インストール:

```bash
uv pip install -r requirements.txt
```

環境を `requirements.txt` と一致させたい場合は以下でも可:

```bash
uv pip sync requirements.txt
```

直接インストールする場合は:

```bash
uv pip install spidev
```

動作確認時には以下のように `spidev 3.8` がビルド・インストールされました。

```text
Resolved 1 package
Built spidev==3.8
Installed 1 package
 + spidev==3.8
```

確認:

```bash
python -c "import spidev; print(spidev)"
```

---

## 8. Read BME280 fixed Chip ID

BME280 の Chip ID register は `0xD0` で、
正常な BME280 では `0x60` が読み出されます。

例:

```python
import spidev

SPI_BUS = 0
SPI_CS = 1
SPI_SPEED_HZ = 500_000
SPI_MODE = 0

spi = spidev.SpiDev()

try:
    spi.open(SPI_BUS, SPI_CS)
    spi.max_speed_hz = SPI_SPEED_HZ
    spi.mode = SPI_MODE
    spi.bits_per_word = 8

    tx = [0xD0, 0x00]

    # xfer2() が渡した list を書き換える場合があるため、
    # 送信値表示用にコピーを保持する。
    tx_log = tx.copy()

    rx = spi.xfer2(tx)

    print("TX:", [f"0x{x:02X}" for x in tx_log])
    print("RX:", [f"0x{x:02X}" for x in rx])
    print(f"Chip ID = 0x{rx[1]:02X}")

finally:
    spi.close()
```

実行:

```bash
python ./read_fixed_register.py
```

期待結果:

```text
TX: ['0xD0', '0x00']
RX: ['0xFF', '0x60']
Chip ID = 0x60
```

`Chip ID = 0x60` が取得できれば、少なくとも以下の基本的な SPI 通信が成立しています。

- Chip Select
- SPI Clock
- MOSI
- MISO
- BME280 register read

### Note about TX display

`spidev.xfer2()` は環境によって渡した list の内容を受信値で上書きするため、

```text
TX: ['0xFF', '0x60']
RX: ['0xFF', '0x60']
```

のように見える場合があります。

これは実際に `0xFF, 0x60` を送信したことを意味するわけではありません。
送信値をログに残す場合は、上記コードのように `tx.copy()` を transfer 前に保存します。

---

## 9. Read temperature / pressure / humidity

Chip ID が正常に取得できた後は、BME280 の calibration data と measurement registers を読み出し、

```text
YYYY-MMDD-hh:mm:ss, temperature(degC), pressure(hPa), humidity(%)
```

の形式で 1 Hz 出力します。

例:

```text
2026-1006-13:21:01,24.57,1008.43,48.31
2026-1006-13:21:02,24.58,1008.42,48.28
2026-1006-13:21:03,24.58,1008.41,48.30
```

---

## 10. Re-create the environment

別の Raspberry Pi や Linux 環境で再構築する場合:

```bash
cd ~/work/bme280

uv python install 3.14
uv venv --python 3.14 .venv
source .venv/bin/activate

uv pip install -r requirements.txt
```

その後、SPI device を確認します。

```bash
ls -l /dev/spidev*
```

例えば、

```text
/dev/spidev0.1
```

であれば:

```python
SPI_BUS = 0
SPI_CS = 1
```

です。

---

## 11. Future Zybo / PetaLinux use

この Python コードは Linux の `/dev/spidevX.Y` を使用しているため、
Zybo / PetaLinux 側でも `spidev` device が生成されれば同じコードを使用できます。

例:

```text
Raspberry Pi
/dev/spidev0.1
       |
       +-- Python + spidev

Zybo / PetaLinux
/dev/spidevX.Y
       |
       +-- same Python code
```

Zybo 側では Device Tree / kernel configuration によって
PS SPI controller と SPI slave device を有効化する必要があります。

Python 側は主に以下だけ変更します。

```python
SPI_BUS = X
SPI_CS = Y
```

---

## Dependency management policy

現時点では依存パッケージが `spidev` だけなので、簡単さを優先して
`requirements.txt` を使用しています。

```text
spidev==3.8
```

プロジェクトが大きくなり、依存関係や Python version を厳密に管理したくなった場合は、

```text
pyproject.toml
uv.lock
```

を使用する uv project 形式へ移行する予定です。
