// 设置那块板上的纯函数（外层 #134）：一家底座 / 一台算力上次检查的状态——一个词、几项事实、一种色调，
// 不是一句话（主人 2026-09-22：能用词就用词，短句也少）；贴进来的 ssh 一行怎么拆、机器名怎么起。
// 都不碰 DOM，vitest 直接测。
import type { AgentCheck, CheckItem, ComputeCheck } from '@/api/types'

export type Tone = 'ok' | 'bad' | 'neutral'

/** 板上一处状态：`word` 是那个词（就绪 / 未登录 / 连接失败 / 未检查），`facts` 是跟在后面的几项短事实
 *  （版本、几秒、多少钱、GPU），`hint` 是没过时机器给的那一句（下一步怎么办），单独一行、小字 */
export interface Status { word: string; tone: Tone; facts: string[]; hint?: string }

const UNCHECKED: Status = { word: '未检查', tone: 'neutral', facts: [] }

/** 四句自检哪一句没过，板上用哪个词 */
const AGENT_FAIL_WORD: Record<string, string> = {
  装了没: '未安装', 版本: '版本过低', 登录: '未登录', 说话: '无响应',
}

/** 一家 coding agent：四句都过了是「就绪」+ 几秒 + 多少钱（订阅没有美元就不写）；第一句没过的那个词 + 机器的原话 */
export function agentStatus(check: AgentCheck | null): Status {
  if (!check) return UNCHECKED
  const failed = check.items.find((item) => !item.ok)
  if (!check.ok || failed) {
    return { word: AGENT_FAIL_WORD[failed?.name ?? ''] ?? '未通过', tone: 'bad', facts: [], hint: failed?.note }
  }
  const facts: string[] = []
  if (check.spoke_s != null) facts.push(`${check.spoke_s.toFixed(1)} s`)
  if (check.cost_usd != null) facts.push(`$${check.cost_usd.toFixed(2)}`)
  return { word: '就绪', tone: 'ok', facts }
}

/** 两种记法摆平：算力的 `[名字, 过没过, 一句话]` 与底座的对象 */
export function checkItem(item: CheckItem): { name: string; ok: boolean; note: string } {
  return Array.isArray(item) ? { name: item[0], ok: item[1], note: item[2] } : item
}

const COMPUTE_FAIL_WORD: Record<string, string> = { 连接: '连接失败' }

/** 一台算力：本机不落盘，没探过是「未检查」；探过是「就绪」+ GPU；没过是那一项的词 + 机器的原话 */
export function computeStatus(check: ComputeCheck | null): Status {
  if (!check) return UNCHECKED
  const failed = (check.items ?? []).map(checkItem).find((item) => !item.ok)
  if (!check.ok || failed) {
    const word = failed ? (COMPUTE_FAIL_WORD[failed.name] ?? `${failed.name}未通过`) : '未通过'
    return { word, tone: 'bad', facts: [], hint: failed?.note }
  }
  return { word: '就绪', tone: 'ok', facts: check.gpu ? [check.gpu] : [] }
}

/** CLI 报的版本串里只留版本号：`2.1.278 (Claude Code)` → `2.1.278`，`codex-cli 0.147.0` → `0.147.0`；认不出原样给 */
export function shortVersion(text: string | undefined): string {
  if (!text) return ''
  return /\d+\.\d+(?:\.\d+)*/.exec(text)?.[0] ?? text
}

const USER_HOST = /^(?<user>[A-Za-z0-9._-]+)@(?<host>[A-Za-z0-9.-]+)(?::(?<port>\d{1,5}))?$/

/** 研究者从算力平台复制来的那一行：`ssh -p 29115 root@host`、`ssh root@host -p 22`、`root@host:22`、`root@host`，
 *  都拆成后端认的 `user@host:port`；认不出返回 null */
export function parseSsh(line: string): string | null {
  const words = line.trim().split(/\s+/).filter((w) => w !== 'ssh')
  let port: string | null = null
  const rest: string[] = []
  for (let i = 0; i < words.length; i += 1) {
    if (words[i] === '-p' && /^\d{1,5}$/.test(words[i + 1] ?? '')) {
      port = words[i + 1]
      i += 1
    } else if (/^-p\d{1,5}$/.test(words[i])) {
      port = words[i].slice(2)
    } else {
      rest.push(words[i])
    }
  }
  if (rest.length !== 1) return null
  const match = USER_HOST.exec(rest[0])
  if (!match?.groups) return null
  const picked = port ?? match.groups.port ?? '22'
  const n = Number(picked)
  if (!(n > 0 && n < 65536)) return null
  return `${match.groups.user}@${match.groups.host}:${picked}`
}

/** 家目录缩成 ~：`/Users/me/x`、`/home/me/x` → `~/x`；别的原样 */
export function tildify(path: string): string {
  return path.replace(/^\/(?:Users|home)\/[^/]+(?=\/|$)/, '~')
}

/** 给机器起名：主机名第一段，小写、只留字母数字连字符；空了就叫 box */
export function suggestComputeName(ssh: string): string {
  const host = ssh.split('@')[1]?.split(':')[0] ?? ''
  const word = host.split('.')[0].toLowerCase().replace(/[^a-z0-9-]/g, '')
  return word || 'box'
}
