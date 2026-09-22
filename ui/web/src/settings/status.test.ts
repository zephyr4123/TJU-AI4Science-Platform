import { describe, expect, it } from 'vitest'

import { agentSentence, computeSentence, parseSsh, suggestComputeName } from './status'

describe('设置：一句话状态', () => {
  it('没检查过、四句都过、有一句没过', () => {
    expect(agentSentence(null)).toEqual({ text: '还没检查', tone: 'neutral' })
    expect(agentSentence({ ok: true, items: [{ name: '装了没', ok: true, note: '/x' }], spoke_s: 0.62, cost_usd: 0.05, at: 't' }))
      .toEqual({ text: '装了，登录了，刚说过话（0.6 秒，$0.050）', tone: 'ok' })
    expect(agentSentence({ ok: true, items: [], spoke_s: 11.2, cost_usd: null, at: 't' }).text)
      .toBe('装了，登录了，刚说过话（11.2 秒）')
    expect(agentSentence({ ok: false, items: [{ name: '装了没', ok: true, note: '/x' },
                                             { name: '登录', ok: false, note: '没登录：在终端跑 codex login' }], at: 't' }))
      .toEqual({ text: '没登录：在终端跑 codex login', tone: 'bad' })
  })
  it('算力：本机没探过、探过带 GPU、没过带原话', () => {
    expect(computeSentence(null).text).toBe('还没检查')
    expect(computeSentence({ ok: true, gpu: 'RTX 4090', items: [], at: 't' })).toEqual({ text: '能用，RTX 4090', tone: 'ok' })
    expect(computeSentence({ ok: false, items: [{ name: '连接', ok: false, note: '连不上（机器关了？）' }], at: 't' }).text)
      .toBe('连不上（机器关了？）')
    // 算力那边记的是三元组（compute.Probe.to_dict），过了的三元组不能被当成没过
    expect(computeSentence({ ok: true, gpu: 'RTX 4090', items: [['连接', true, '1.7 s'], ['GPU', true, 'RTX 4090']], at: 't' }).tone)
      .toBe('ok')
    expect(computeSentence({ ok: false, items: [['连接', false, '连不上']], at: 't' })).toEqual({ text: '连不上', tone: 'bad' })
  })
})

describe('设置：贴进来的 ssh 一行', () => {
  it('四种写法都拆成 user@host:port', () => {
    expect(parseSsh('ssh -p 29115 root@connect.example.com')).toBe('root@connect.example.com:29115')
    expect(parseSsh('ssh root@h.example.org -p 22')).toBe('root@h.example.org:22')
    expect(parseSsh('  root@10.0.0.2:2222 ')).toBe('root@10.0.0.2:2222')
    expect(parseSsh('u@host')).toBe('u@host:22')
  })
  it('认不出的返回 null', () => {
    expect(parseSsh('')).toBeNull()
    expect(parseSsh('ssh')).toBeNull()
    expect(parseSsh('root@host -p 99999')).toBeNull()
    expect(parseSsh('root host')).toBeNull()
    expect(parseSsh('root@host extra')).toBeNull()
  })
  it('机器名从主机名第一段来', () => {
    expect(suggestComputeName('root@connect.westb.seetacloud.com:29115')).toBe('connect')
    expect(suggestComputeName('u@GPU_Box.local:22')).toBe('gpubox')
    expect(suggestComputeName('nonsense')).toBe('box')
  })
})
