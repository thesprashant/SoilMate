import { build } from 'esbuild'
import { spawnSync } from 'node:child_process'
await build({ entryPoints: ['./tests/ui.test.jsx'], outfile: './tests/generated-ui.test.mjs', bundle: true, platform: 'node', format: 'esm', packages: 'external' })
const result = spawnSync(process.execPath, ['--test', 'tests/api.test.mjs', 'tests/generated-ui.test.mjs'], { stdio: 'inherit' })
process.exitCode = result.status ?? 1
