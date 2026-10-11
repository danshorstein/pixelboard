# Hardware build

The documented prototype is an assembled, owner-tested sports display. The
final V5 rear enclosure was printed as three separate pieces; the owner confirms
all three fit the display back and screw into place.

## Parts used

| Part | Documented build |
| --- | --- |
| Display | Two chained 64×32 P4 HUB75 RGB panels; exact panel model is not recorded |
| Computer | Raspberry Pi 3 Model A+ |
| Matrix interface | Adafruit RGB Matrix Bonnet/HAT, product 3211 |
| Panel power | Separate regulated 5 V supply; the wiring record specifies 10 A |
| Pi power | Separate 5 V, 2.5 A Micro-USB supply |
| Controls | 8BitDo Zero 2 Bluetooth remote in keyboard mode |
| Storage | microSD card; exact model and capacity are not recorded |
| Rear enclosure | Accepted V5 three-piece shell; see [print plates](frame-v5/accepted/README.md) |
| Fasteners and cables | M3 mounting screws, HUB75 ribbon cables, and panel power leads; use the tested arrangement |

The BOM lists compatible reference part numbers separately from installed parts
where the exact manufacturer model is not recorded. It contains no price or
availability claims.

## Print the accepted rear shell

Use the three plates in `frame-v5/accepted/`:

1. Print the left, center, and right pieces from Plates 1–3.
2. Fit the center section across the seam between the two panels.
3. Slide the left and right sections into the center section's alignment tabs.
4. Fasten the sections with the tested hardware, tightening evenly by hand.

The recorded profile is Bambu Lab A1 mini with PLA and no supports. Check the
[plate notes](frame-v5/accepted/README.md) for print-source details. The files
are offered under CERN-OHL-S-2.0.
