# Vendored files

Served from here, never from a CDN: the UI makes no external requests.

## Apache ECharts 6.1.0 (`echarts/`)

- Source: the npm package, <https://registry.npmjs.org/echarts/-/echarts-6.1.0.tgz>
- Tarball integrity, as published by the registry (sha512, base64):
  `q0yaFPggC9FUdsWH4blavRWFmxdrIodbkoKNAjJudAI6CA9gNPxHtV2RcZNEepZVlk4yvBYkOkbk6HIVpIyHZA==`
- `echarts.esm.min.js` is `dist/echarts.esm.min.js`, unchanged.
  sha256: 28515f26aa57f87eb1e4ed4eb446927eaf329b5f5e02b4bfd4b0264fea40d1da
- `LICENSE`, `NOTICE`, `licenses/LICENSE-d3` are copied from the same paths in the package.
  ECharts is Apache-2.0; the parts of d3 it embeds are BSD-3-Clause.

To update: download the new tarball, compare it with the integrity value from
`https://registry.npmjs.org/echarts/<version>`, copy the same four files, update this file, and
draw a chart in the browser to check it still works under the Content-Security-Policy.
