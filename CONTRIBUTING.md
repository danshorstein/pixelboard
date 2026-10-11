# Contributing

Thanks for helping improve Pixelboard. Keep changes focused and preserve the
TypeScript/Python rendering parity for shared display code.

Before opening a pull request, run:

```bash
npm test
npm run test:py
```

For rendering changes, also run the device verification command described in
the device package documentation and include the generated comparison result.
Use synthetic fixtures. Never commit household settings, calendar URLs,
device state, private images, or credentials.

The public `main` branch is the shared development line. Device updates should
use reviewed, tagged releases rather than deploying every merge automatically.
