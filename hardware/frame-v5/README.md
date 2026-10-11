# Pixelboard rear enclosure V5 — accepted direct-mount three-piece design

The owner confirms the final V5 design was printed as three separate rear
pieces; all three fit the display back and screwed into place as intended.
This physical confirmation supersedes earlier draft status in the design
notes. The final local 3MF plate exports are included in [`accepted/`](accepted/README.md).

V5 replaces the rejected V4 attachment scheme. It uses no temporary V3 splice
plates or captive nuts. Its outside outline is **exactly 511 × 126.5 mm**, the
same as the physically fitted V3 frame. There is no outer lip, and the 3 mm
perimeter wall has no additional inward shift.

The Bambu A1 Mini prints three approximately 170 mm wide shell sections. The
middle section is one continuous piece across the seam between the two LED
panels. Each section has four paths aligned to the existing LED-panel screw
holes. The center section's four direct anchors hold both LED panels in the
same rear piece. The two shell joins are away from the LED panel seam. Each
join now has two small rear-skin tabs that slide into matching notches in the
next section, so the printed pieces register before tightening. The tabs stay
within the 511 × 126.5 mm outside outline; they are alignment aids, while the
panel screws carry the load. There are no separate splice plates.

## Fasteners

The owner confirms that the three printed sections screwed into place as
intended. The V5 design uses M3 × 30 screws; reuse the tested arrangement
when reproducing it. Tightening torque was not recorded.

## Mount positions

- Left: x=7.425 and 127.425 mm, upper and lower rows.
- Center: x=247.425 and 263.575 mm, upper and lower rows.
- Right: x=383.575 and 503.575 mm, upper and lower rows.

The lower hole at x=127.425 mm shares the mounting area with the installed
Raspberry Pi. The owner confirms the completed rear assembly fit and fastened
correctly. Use the tested hardware arrangement when reproducing it; the exact
fastener lengths and tightening torque are not recorded here.

The lower wall has a rear-open power-cord slot near x=150 mm. Its rounded cable
seat is at z=22 mm, around the middle of the 40 mm cavity, leaving 16 mm of
solid wall next to the LED panel. Lay the cable into the slot from the back;
the plug does not have to pass through the opening. The owner reports the rear
design fit as intended. The exact cable-retention arrangement is not recorded
in this repository.

Each of the three current print plates contains only one shell section. Plate
1 is left, Plate 2 is the one-piece center, and Plate 3 is right. No small
loose parts are needed for this shell fit trial.

## Assembly

The owner confirmed the three printed sections fasten to the rear as designed.
For a reproduction, support the display face-down, align the center section
across the panel seam, slide the side sections into its alignment tabs, and
fasten them with the hardware used in the accepted build. Tighten by hand
evenly; do not use screw force to correct misalignment.

The owner has physically accepted the complete three-piece rear fit. The
accepted print exports are included. The editable CAD source still depends on
modules in a separate local design pipeline and needs to be made portable.
