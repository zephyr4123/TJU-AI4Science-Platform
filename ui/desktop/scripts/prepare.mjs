// 准备构建输入（spec desktop.md §6，外层 #282）：图标与 uv sidecar 都在构建时生成、不进 git（P-17）。
// tauri-build 在编译期就要它们在（缺 externalBin 报 ResourcePathNotFound、Windows 缺 icon.ico 报错），
// 所以 dev / check / build 第一步都先跑这里（scripts/run.mjs）。
//
//   node scripts/prepare.mjs
//       图标 + 把仓里 .venv 的 uv 放成本机三元组的 sidecar（与 uv.lock 是同一版）
//   node scripts/prepare.mjs --uv-version 0.12.18 --target universal-apple-darwin
//       发版用：从 uv 的 GitHub 发布取这个三元组（universal 取两种架构）、核 .sha256、Mac 上 lipo 合成
//
// 图标从页面的品牌标 ui/web/public/favicon.svg 来：同三条路径、浅色那组颜色，垫在白色圆角方块上。
import { createHash } from 'node:crypto'
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
export const DESKTOP = resolve(HERE, '..')
export const REPO = resolve(DESKTOP, '..', '..')
const TAURI = join(DESKTOP, 'src-tauri')
const ICONS = join(TAURI, 'icons')
const BINARIES = join(TAURI, 'binaries')
const FAVICON = join(REPO, 'ui', 'web', 'public', 'favicon.svg')
const TAURI_CLI = join(DESKTOP, 'node_modules', '@tauri-apps', 'cli', 'tauri.js')
const UV_RELEASES = 'https://github.com/astral-sh/uv/releases/download'
const UNIVERSAL = 'universal-apple-darwin'
const WINDOWS = process.platform === 'win32'

// 1024 画布、824 的圆角方块（macOS 图标的网格：四周留 100 给系统的投影），标占方块的六成多
const CANVAS = 1024
const TILE = { at: 100, size: 824, radius: 185 }
const MARK = { size: 560, viewBox: 64 }

export function run(cmd, args, options = {}) {
  const done = spawnSync(cmd, args, { stdio: 'inherit', ...options })
  if (done.error) throw new Error(`${cmd} 起不来：${done.error.message}`)
  if (done.status !== 0) throw new Error(`${cmd} ${args.join(' ')} 退出码 ${done.status}`)
}

/** 页面的标：三条路径与浅色（style 里 @media 之前那组）。 */
export function readMark(svg) {
  const paths = [...svg.matchAll(/<path class="([abc])" d="([^"]+)"\/>/g)].map(([, cls, d]) => ({ cls, d }))
  const light = svg.split('@media')[0]
  const fill = cls => light.match(new RegExp(`\\.${cls}\\{fill:(#[0-9A-Fa-f]{6})\\}`))?.[1]
  if (paths.length !== 3 || paths.some(p => !fill(p.cls))) throw new Error(`${FAVICON} 里读不出三条路径与颜色`)
  return paths.map(p => ({ d: p.d, fill: fill(p.cls) }))
}

export function appIconSvg(mark) {
  const scale = MARK.size / MARK.viewBox
  const offset = (CANVAS - MARK.size) / 2
  const paths = mark.map(p => `<path fill="${p.fill}" d="${p.d}"/>`).join('')
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${CANVAS} ${CANVAS}">`
    + `<rect x="${TILE.at}" y="${TILE.at}" width="${TILE.size}" height="${TILE.size}" rx="${TILE.radius}" fill="#FFFFFF" stroke="#E3E6EC" stroke-width="4"/>`
    + `<g transform="translate(${offset} ${offset}) scale(${scale})">${paths}</g></svg>\n`
}

function newer(target, ...sources) {
  return existsSync(target) && sources.every(s => statSync(s).mtimeMs <= statSync(target).mtimeMs)
}

function icons() {
  const self = fileURLToPath(import.meta.url)
  if (newer(join(ICONS, 'icon.icns'), FAVICON, self) && newer(join(ICONS, 'icon.ico'), FAVICON, self)) return
  mkdirSync(ICONS, { recursive: true })
  const source = join(ICONS, 'app-icon.svg')
  writeFileSync(source, appIconSvg(readMark(readFileSync(FAVICON, 'utf8'))))
  run(process.execPath, [TAURI_CLI, 'icon', source, '--output', ICONS], { cwd: DESKTOP })
}

export function hostTriple() {
  const done = spawnSync('rustc', ['-vV'], { encoding: 'utf8' })
  const host = done.stdout?.match(/^host: (\S+)$/m)?.[1]
  if (!host) throw new Error('rustc -vV 读不出本机三元组：先装 Rust（ui/desktop/README.md）')
  return host
}

const sidecarName = triple => `uv-${triple}${triple.includes('windows') ? '.exe' : ''}`

/** 缺省：仓里 .venv 的 uv（uv.lock 钉的那一版）放成本机三元组的 sidecar。 */
function sidecarFromVenv() {
  const uv = join(REPO, '.venv', WINDOWS ? 'Scripts' : 'bin', WINDOWS ? 'uv.exe' : 'uv')
  if (!existsSync(uv)) throw new Error(`没有 ${uv}：先在仓根 make venv（Windows：uv sync --locked）`)
  const dest = join(BINARIES, sidecarName(hostTriple()))
  if (existsSync(dest) && statSync(dest).size === statSync(uv).size && newer(dest, uv)) return
  mkdirSync(BINARIES, { recursive: true })
  copyFileSync(uv, dest)
}

const sha256 = bytes => createHash('sha256').update(bytes).digest('hex')

async function fetchBytes(url) {
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(`取不到 ${url}：HTTP ${resp.status}`)
  return Buffer.from(await resp.arrayBuffer())
}

/** 一个三元组的 uv：取发布包与它旁边的 .sha256，对上了才解出来。下载的东西放在自己的空目录里。 */
async function uvFromRelease(version, triple, work) {
  const archive = `uv-${triple}${triple.includes('windows') ? '.zip' : '.tar.gz'}`
  const bytes = await fetchBytes(`${UV_RELEASES}/${version}/${archive}`)
  const want = (await fetchBytes(`${UV_RELEASES}/${version}/${archive}.sha256`)).toString('utf8').trim().split(/\s+/)[0]
  if (sha256(bytes) !== want) throw new Error(`${archive} 与它的 .sha256 对不上`)
  const dir = mkdtempSync(join(work, `${triple}-`))
  writeFileSync(join(dir, archive), bytes)
  run('tar', ['-xf', archive], { cwd: dir })  // Windows 10 起自带的 tar 也解 zip
  const exe = triple.includes('windows') ? join(dir, 'uv.exe') : join(dir, `uv-${triple}`, 'uv')
  if (!existsSync(exe)) throw new Error(`${archive} 里没有 uv`)
  return exe
}

async function sidecarFromRelease(version, target) {
  const work = mkdtempSync(join(tmpdir(), 'aaai4s-uv-'))
  try {
    mkdirSync(BINARIES, { recursive: true })
    const dest = join(BINARIES, sidecarName(target))
    if (target === UNIVERSAL) {
      // 通用包是两种架构各编一遍再合：编每一遍时 tauri-build 要那个架构自己的 sidecar，打包时要合成的那份
      const slices = []
      for (const arch of ['aarch64-apple-darwin', 'x86_64-apple-darwin']) {
        const slice = await uvFromRelease(version, arch, work)
        copyFileSync(slice, join(BINARIES, sidecarName(arch)))
        slices.push(slice)
      }
      run('lipo', ['-create', '-output', dest, ...slices])
    } else {
      copyFileSync(await uvFromRelease(version, target, work), dest)
    }
    console.log(`sidecar ${dest}（uv ${version}）`)
  } finally {
    rmSync(work, { recursive: true, force: true })
  }
}

function option(args, name) {
  const at = args.indexOf(name)
  return at >= 0 ? args[at + 1] : undefined
}

export async function prepare(args = []) {
  icons()
  const version = option(args, '--uv-version')
  const target = option(args, '--target')
  if (version || target) {
    if (!version || !target) throw new Error('--uv-version 与 --target 要一起给')
    await sidecarFromRelease(version, target)
  } else {
    sidecarFromVenv()
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  prepare(process.argv.slice(2)).catch(error => {
    console.error(`prepare：${error.message}`)
    process.exit(1)
  })
}
