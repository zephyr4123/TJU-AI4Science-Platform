// 启动页的脚本：载入时向外壳要这一屏的样子（attach 一个 Channel，先给全貌、再给增量），照着改。
// 只调外壳那四条命令，不传任何路径与地址；外壳给的字一律 textContent，不拼 HTML（src-tauri/tests/splash.rs 查）。
// 以模块载入：自己一个作用域，不往全局放东西。

const { invoke, Channel } = window.__TAURI__.core

/** 标记的颜色：好了是铜绿、没装好是红、要注意是琥珀、还在下是靛 */
const MARKS = { '✓': 'm-ok', '✗': 'm-bad', '!': 'm-wait', '…': 'm-busy', '↓': 'm-busy' }

const $ = id => document.getElementById(id)
const rows = new Map() // 标签 → 那一行：同一标签后来的行就地换掉
let startedAt = Date.now()
let ticking = 0

function clock() {
  const s = Math.max(0, Math.floor((Date.now() - startedAt) / 1000))
  $('elapsed').textContent = `已用 ${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

function tick(running) {
  clearInterval(ticking)
  clock()
  ticking = running ? setInterval(clock, 1000) : 0
}

function row({ mark, label, note }) {
  let line = rows.get(label)
  if (!line) {
    line = document.createElement('li')
    for (const part of ['mark', 'label', 'note']) {
      const span = document.createElement('span')
      span.className = part
      line.append(span)
    }
    rows.set(label, line)
    $('rows').append(line)
  }
  const [markEl, labelEl, noteEl] = line.children
  markEl.textContent = mark
  markEl.className = `mark ${MARKS[mark] ?? ''}`
  labelEl.textContent = label
  noteEl.textContent = note
}

function problem(found) {
  $('problem').hidden = !found
  if (!found) return
  tick(false)
  $('problem-text').textContent = found.text
  $('retry').hidden = !found.retry
  $('webview2').hidden = !found.webview2
}

function apply(event) {
  switch (event.kind) {
    case 'snapshot':
      rows.clear()
      $('rows').replaceChildren()
      $('status').textContent = event.status
      event.rows.forEach(row)
      startedAt = event.startedAt
      tick(!event.problem)
      problem(event.problem)
      break
    case 'status':
      $('status').textContent = event.text
      break
    case 'row':
      row(event.row)
      break
    case 'problem':
      problem(event.problem)
      break
  }
}

/** 调不通外壳（不该发生）：原话进控制台，屏上只说一句、停表 */
function broken(error) {
  console.error(error)
  problem({ text: '桌面 App 出错了：退出再打开试试', retry: false })
}

function call(command) {
  invoke(command).catch(broken)
}

const channel = new Channel()
channel.onmessage = apply
invoke('attach', { onEvent: channel }).catch(broken)
tick(true)

$('retry').addEventListener('click', () => call('retry'))
$('open-log').addEventListener('click', () => call('open_log'))
$('webview2').addEventListener('click', () => call('open_webview2_download'))
