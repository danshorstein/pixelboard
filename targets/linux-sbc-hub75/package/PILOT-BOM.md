# Pixelboard prototype bill of materials

This inventory records the assembled prototype and the documented reference
parts. A reference number helps identify a compatible replacement; it does not
prove the installed unit came from that supplier. Prices and stock are omitted
because they change.

| Qty | Part | Prototype record | Reference part |
| ---: | --- | --- | --- |
| 2 | 64×32 P4 HUB75 RGB LED panels | Two chained panels make the 128×32 display. Exact panel label/model is not recorded. | Adafruit 2278 is the documented compatible reference. |
| 1 | Raspberry Pi 3 Model A+ | Installed computer. | Adafruit 4027. |
| 1 | RGB Matrix Bonnet/HAT | Installed level-shifting HUB75 interface. | Adafruit 3211. |
| 1 | Regulated 5 V panel supply | Separate supply for both panels; the pilot wiring record specifies 10 A. Exact installed model is not recorded. | Adafruit 658 is the documented reference. |
| 1 | Raspberry Pi power supply | Separate 5 V, 2.5 A Micro-USB supply. Exact installed model is not recorded. | Adafruit 1995 is the documented reference. |
| 1 | Bluetooth keyboard-style remote | The accepted controller is an 8BitDo Zero 2 in keyboard mode. | 8BitDo Zero 2. |
| 1 | microSD card | Raspberry Pi OS compatible; exact card and capacity are not recorded. | Use a reliable, high-endurance card. |
| 3 | V5 rear enclosure pieces | The owner confirms the final three pieces fit the back and screwed into place. The three print plates are included under `hardware/frame-v5/accepted/`. | The accepted 3MF plate exports are included. |
| as needed | M3 mounting screws and power/signal cables | The V5 design uses M3 × 30 screws; use the tested arrangement and suitable rated cables. | Match the panel and Bonnet connectors. |

Keep the panel supply separate from the Pi supply. Never route panel current
through the Pi. Verify polarity, connector fit, wire rating, and strain relief
before powering the assembly.
