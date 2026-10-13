# Third-party notices

## OpenChamber

Used by: `web/src/styles/tokens.css` (colour palette, typography scale and control geometry).

The workspace theme adapts colour values and sizing from the OpenChamber `openchamber-light` and `openchamber-dark` themes at revision `02306f32e4d191e4840440cbafa643ae899471c2`, through the `omms-design` design guidance. No OpenChamber application code is included. Two values are local adaptations: the focus ring uses the opaque accent, and the dark tinted-button label uses the dark pressed accent (`#fd9b66`) to meet WCAG AA contrast on the strongest tint.

Source: <https://github.com/openchamber/openchamber>

```text
MIT License

Copyright (c) 2025 Bohdan Triapitsyn

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Bundled runtime packages

Used by: the built application in `src/omrg/transports/api/static/`. The production build (`npm run build`) bundles these npm packages into one script file. The build removes their licence comments, so their notices are kept here. Development-only packages (test, lint and type tools, `@types/*`) are not bundled and are not listed.

Versions are from `web/package-lock.json` on 2026-10-13. Update this list when a runtime dependency changes.

| Package | Version | Licence | Copyright |
|---|---|---|---|
| `react` | 19.3.0 | MIT | Copyright (c) Meta Platforms, Inc. and affiliates. |
| `react-dom` | 19.3.0 | MIT | Copyright (c) Meta Platforms, Inc. and affiliates. |
| `scheduler` | 0.28.0 | MIT | Copyright (c) Meta Platforms, Inc. and affiliates. |
| `use-sync-external-store` | 1.7.0 | MIT | Copyright (c) Meta Platforms, Inc. and affiliates. |
| `@xyflow/react` | 12.12.0 | MIT | Copyright (c) 2019-2025 webkid GmbH |
| `@xyflow/system` | 0.0.83 | MIT | Copyright (c) 2019-2025 webkid GmbH |
| `zustand` | 4.5.7 | MIT | Copyright (c) 2019 Paul Henschel |
| `classcat` | 5.0.5 | MIT | Copyright © Jorge Bucaran <https://jorgebucaran.com> |
| `d3-color` | 3.1.0 | ISC | Copyright 2010-2022 Mike Bostock |
| `d3-dispatch` | 3.0.1 | ISC | Copyright 2010-2021 Mike Bostock |
| `d3-drag` | 3.0.0 | ISC | Copyright 2010-2021 Mike Bostock |
| `d3-interpolate` | 3.0.1 | ISC | Copyright 2010-2021 Mike Bostock |
| `d3-selection` | 3.0.0 | ISC | Copyright 2010-2021 Mike Bostock |
| `d3-timer` | 3.0.1 | ISC | Copyright 2010-2021 Mike Bostock |
| `d3-transition` | 3.0.1 | ISC | Copyright 2010-2021 Mike Bostock |
| `d3-zoom` | 3.0.0 | ISC | Copyright 2010-2021 Mike Bostock |
| `d3-ease` | 3.0.1 | BSD-3-Clause | Copyright 2010-2021 Mike Bostock; Copyright 2001 Robert Penner |

The canvas keeps the React Flow attribution link that `@xyflow/react` shows by default.

### MIT licence (applies with each copyright line above marked MIT)

```text
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### ISC licence (applies with each copyright line above marked ISC)

```text
Permission to use, copy, modify, and/or distribute this software for any purpose
with or without fee is hereby granted, provided that the above copyright notice
and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER
TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF
THIS SOFTWARE.
```

### BSD 3-Clause licence (`d3-ease`)

```text
Copyright 2010-2021 Mike Bostock
Copyright 2001 Robert Penner
All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

* Neither the name of the author nor the names of contributors may be used to
  endorse or promote products derived from this software without specific prior
  written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

## Screenshots

The images in `docs/guides/images/web-workspace/` are captures of this application with synthetic sources. They contain no third-party material other than the bundled packages above.
