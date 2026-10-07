// 外壳的三条命令（spec desktop.md §6）：package.json 的 dev / check / build 都转到这里，跨平台的真入口；
// Makefile 在 Mac 上只转调 npm，Windows 上直接 `npm --prefix ui/desktop run <命令>`。
//
//   dev    源码桌面：后端用仓里 .venv 的 ai4sci（AI4SCI_DESKTOP_CLI，已设的照用），identifier 换成 .dev，
//          不与装好的 App 抢单实例与配置目录
//   check  外壳的门禁：cargo fmt --check、clippy -D warnings、cargo test，配置里不许有 remote-debugging
//   build  本机出安装包；Mac 上设 CI=true（不然打 DMG 时卡在 Finder 的自动化授权）
// 后面多给的参数原样交给 tauri（例如 `npm run build -- --target universal-apple-darwin`）。
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { DESKTOP, REPO, prepare, run } from './prepare.mjs'

const TAURI = join(DESKTOP, 'src-tauri')
const MANIFEST = ['--manifest-path', join(TAURI, 'Cargo.toml')]
const TAURI_CLI = join(DESKTOP, 'node_modules', '@tauri-apps', 'cli', 'tauri.js')
const DEV_IDENTIFIER = 'com.zephyrxiang.aaai4s.dev'
const WINDOWS = process.platform === 'win32'

const tauri = (args, env = process.env) => run(process.execPath, [TAURI_CLI, ...args], { cwd: DESKTOP, env })

function dev(rest) {
  const cli = join(REPO, '.venv', WINDOWS ? 'Scripts' : 'bin', WINDOWS ? 'ai4sci.exe' : 'ai4sci')
  const env = { ...process.env }
  env.AI4SCI_DESKTOP_CLI ??= cli
  if (!existsSync(env.AI4SCI_DESKTOP_CLI)) throw new Error(`没有 ${env.AI4SCI_DESKTOP_CLI}：先在仓根 make venv`)
  tauri(['dev', '--config', JSON.stringify({ identifier: DEV_IDENTIFIER }), ...rest], env)
}

/** 配置里出现就等于开了调试端口：谁连上它谁就能在启动页里调外壳的命令、读到页面里的 key（spec §4）。 */
export const forbidden = text => /remote-debugging|tauri-plugin-wdio/i.test(text)

function noDebugPorts() {
  if (!forbidden('"additionalBrowserArgs": "--remote-debugging-port=9222"')) throw new Error('检查器抓不到调试端口')
  const files = readdirSync(TAURI).filter(name => /^tauri.*\.conf\.json$/.test(name)).map(name => join(TAURI, name))
  if (files.length === 0) throw new Error(`${TAURI} 下没有 tauri.conf.json`)
  const bad = [...files, join(TAURI, 'Cargo.toml'), join(TAURI, 'Cargo.lock')].filter(f => forbidden(readFileSync(f, 'utf8')))
  if (bad.length) throw new Error(`正式配置里不许开调试端口或测试驱动：${bad.join('、')}`)
  const cargo = readFileSync(join(TAURI, 'Cargo.toml'), 'utf8')
  if (/^tauri = .*"devtools"/m.test(cargo)) throw new Error('正式包不开 devtools（Cargo.toml 里 tauri 的 features）')
}

function check() {
  noDebugPorts()
  run('cargo', ['fmt', ...MANIFEST, '--check'], { cwd: DESKTOP })
  run('cargo', ['clippy', ...MANIFEST, '--all-targets', '--', '-D', 'warnings'], { cwd: DESKTOP })
  run('cargo', ['test', ...MANIFEST], { cwd: DESKTOP })
}

function build(rest) {
  const env = { ...process.env }
  if (process.platform === 'darwin') env.CI = 'true'
  const extra = []
  if (!env.TAURI_SIGNING_PRIVATE_KEY) {
    // 本机没有更新器的私钥：照样出安装包，只是不出外壳更新用的 .tar.gz / .sig
    console.log('没有 TAURI_SIGNING_PRIVATE_KEY：这次不出外壳更新包')
    extra.push('--config', JSON.stringify({ bundle: { createUpdaterArtifacts: false } }))
  }
  tauri(['build', ...extra, ...rest], env)
}

const [task, ...rest] = process.argv.slice(2)
const tasks = { dev, check, build }
try {
  if (!tasks[task]) throw new Error(`用法：node scripts/run.mjs ${Object.keys(tasks).join(' | ')}`)
  await prepare()
  tasks[task](rest)
} catch (error) {
  console.error(error.message)
  process.exit(1)
}
