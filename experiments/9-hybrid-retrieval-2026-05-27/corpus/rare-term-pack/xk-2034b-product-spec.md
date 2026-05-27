# Internal product spec — XK-2034b sensor module

The **XK-2034b** is the second-revision indoor air-quality sensor module shipped
to OEM partners under contract IAQ-MOD-2024-Q3. It supersedes the XK-2034a
(deprecated 2025-08) and is pin-compatible with the legacy XK-2032 series, but
adds an SCD41 NDIR CO₂ element and a higher-resolution VOC channel.

## Mechanical

- Footprint: 28.0 × 18.0 mm
- Connector: 6-pin JST SH 1.0 mm pitch
- Weight: 1.4 g

## Electrical

- Supply: 3.0–3.6 V DC, typical 3.3 V
- Quiescent current: 38 µA, peak 4.2 mA during NDIR sample
- I²C bus, 7-bit address `0x62` (SCD41) and `0x59` (SGP41 VOC)

## Calibration

The **XK-2034b** ships with a factory-calibrated baseline. Field re-calibration
can be triggered by writing `0x21B7` to the SCD41 reference register after a
10-minute stable exposure to outdoor air. Do not run a factory reset unless
the partner integration manual explicitly requires it; doing so on an
**XK-2034b** with firmware below 0.4.7 will brick the SGP41 channel and
require an RMA.

## Compatibility

| Host           | Driver           | Status        |
| -------------- | ---------------- | ------------- |
| Linux 5.15+    | `iio-scd4x`      | Production    |
| Zephyr 3.4+    | `sensor-scd4x`   | Production    |
| ESP-IDF 5.1+   | `esp-scd4x`      | Beta          |

If you have an integration question specifically about the **XK-2034b**, file
a ticket against project `IAQ-MOD-CHASSIS` and tag the firmware version. The
earlier XK-2034a tickets are not portable to **XK-2034b** because the I²C
address layout was reshuffled.
