# Hardware assembly guide

This guide describes the documented two-panel prototype. Confirm connector
labels and physical measurements on your parts before assembly; panel and
Bonnet revisions can vary.

## Connect the display

1. Power off and unplug the Pi and both supplies.
2. Seat the RGB Matrix Bonnet/HAT squarely on the Pi's 40-pin header. Use an
   insulating spacer where needed to prevent contact with other connectors.
3. Connect the Bonnet HUB75 output to the first panel's `IN` connector.
4. Connect that panel's `OUT` to the second panel's `IN`. Leave the final
   `OUT` connector empty. Follow the arrows and pin-1 marks on the parts.
5. Connect panel power leads to the Bonnet's rated panel-power terminals,
   observing red `+5 V` and black `GND`. Use the correct gauge and secure each
   conductor. If the board does not provide the right terminals, use a rated
   fused distribution block instead.
6. Power the Pi from its own supply. Keep the panel supply separate.

## Fit the rear enclosure

The accepted V5 rear shell is printed as three pieces: left, center, and right.
The center section spans the seam between the panels; the other sections align
with the center tabs. The owner confirms the three pieces fit and screw into
place. Use the included 3MF plates and the same mounting arrangement as the
tested prototype. Tighten evenly by hand; do not force a misaligned piece.

## Pair the remote and test

Pair the Bluetooth remote using the operating system's Bluetooth settings.
Then install the Pixelboard package and run the display diagnostics before
closing the rear shell. Verify panel order, color, brightness, remote controls,
power temperature, and cable clearance on the actual build.

Keep mains connections enclosed and strain-relieved. Disconnect power before
changing any wiring.
