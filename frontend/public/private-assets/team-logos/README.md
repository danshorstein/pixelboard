# Optional local team logos

Pixelboard renders team colors and abbreviation badges by default. You may add
transparent PNG logos here when you have permission to use them. Copy
`manifest.example.json` to the locally ignored `manifest.json`, add the image
files, and fill in each image's dimensions, checksum, source, and usage status.

The classic 128×32 layouts use 16×16 sprites. Larger profiles may use 20×20
or 24×24 masters. Game screens use logo layout only when both teams have valid
assets, so a missing image never creates an unbalanced matchup. Invalid files
fall back to team colors and abbreviation badges.

The repository intentionally contains no team marks. This local directory is
ignored for image and manifest files so that user supplied marks and their
rights records are not committed accidentally. Review `THIRD_PARTY_NOTICES.md`
before packaging or sharing an artifact containing third-party marks.
