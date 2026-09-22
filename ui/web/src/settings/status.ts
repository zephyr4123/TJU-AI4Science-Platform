// 设置那块板上的纯函数（外层 #134）：机器说的一句话状态（不是徽章）、贴进来的 ssh 一行怎么拆、机器名怎么起。
// 都不碰 DOM，vitest 直接测。
import type { AgentCheck, CheckItem, ComputeCheck } from '@/api/types'

export type Tone = 'ok' | 'bad' | 'neutral'

export interface Sentence { text: string; tone: Tone }

/** 一家 coding agent 上次检查的一句话：没检查过 / 四句都过了（几秒、多少钱）/ 第一句没过的原话（它自带下一步） */
export function agentSentence(check: AgentCheck | null): Sentence {
  if (!check) return { text: '还没检查', tone: 'neutral' }
  const failed = check.items.find((item) => !item.ok)
  if (!check.ok || failed) return { text: failed?.note ?? '检查没过', tone: 'bad' }
  const parts = ['装了', '登录了']
  if (check.spoke_s != null) {
    const cost = check.cost_usd != null ? `，$${check.cost_usd.toFixed(3)}` : ''
    parts.push(`刚说过话（${check.spoke_s.toFixed(1)} 秒${cost}）`)
  }
  return { text: parts.join('，'), tone: 'ok' }
}

/** 两种记法摆平：算力的 `[名字, 过没过, 一句话]` 与底座的对象 */
export function checkItem(item: CheckItem): { name: string; ok: boolean; note: string } {
  return Array.isArray(item) ? { name: item[0], ok: item[1], note: item[2] } : item
}

/** 一台算力上次探测的一句话：本机不落盘，没探过就写「还没检查」；探过写 GPU；没过写第一项没过的原话 */
export function computeSentence(check: ComputeCheck | null): Sentence {
  if (!check) return { text: '还没检查', tone: 'neutral' }
  const failed = (check.items ?? []).map(checkItem).find((item) => !item.ok)
  if (!check.ok || failed) return { text: failed?.note ?? '检查没过', tone: 'bad' }
  return { text: check.gpu ? `能用，${check.gpu}` : '能用', tone: 'ok' }
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

/** 给机器起名：主机名第一段，小写、只留字母数字连字符；空了就叫 box */
export function suggestComputeName(ssh: string): string {
  const host = ssh.split('@')[1]?.split(':')[0] ?? ''
  const word = host.split('.')[0].toLowerCase().replace(/[^a-z0-9-]/g, '')
  return word || 'box'
}
