# Pinned matrix driver source archive

- Upstream: <https://github.com/hzeller/rpi-rgb-led-matrix>
- Commit: `e947417fff9042b3ea173542be09490acab069f7`
- Original GitHub archive SHA-256:
  `d6e95802479b5a77400cfe35d24a834a485e1cfe4bfb9f74d3a7c8073f9e0eef`
- Packaged source archive SHA-256:
  `a7862de04d63d501e734c1fe5f95ae3714903b40241d087680625b64147c11fa`

The packaged source archive is the exact upstream commit with two large,
optional, prebuilt Raspberry Pi real-time-kernel binary tarballs removed from
`RT-kernel/`. Their documentation and source repository content remain. Those
kernel images are not used to build or run Scoreboard, and no driver source,
headers, Python bindings, build scripts, license text, examples, hardware
design files, fonts, or documentation were removed.

The archive is included in every device artifact, checksummed by its manifest,
verified before extraction by `install.sh`, retained on the installed device,
and used directly to build the Python binding. Installation does not clone or
fetch mutable driver source.
