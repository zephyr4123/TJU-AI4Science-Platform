import { describe, expect, it } from 'vitest'

import { agentStatus, computeStatus, parseSsh, shortVersion, suggestComputeName, tildify } from './status'

describe('设置：一个词的状态', () => {
  it('底座：没检查过、四句都过、有一句没过', () => {
    expect(agentStatus(null)).toEqual({ word: '未检查', tone: 'neutral', facts: [] })
    expect(agentStatus({ ok: true, items: [{ name: '装了没', ok: true, note: '/x' }], spoke_s: 0.62, cost_usd: 0.05, at: 't' }))
      .toEqual({ word: '就绪', tone: 'ok', facts: ['0.6 s', '$0.05'] })
    // 订阅账号没有美元：不写
    expect(agentStatus({ ok: true, items: [], spoke_s: 11.2, cost_usd: null, at: 't' }).facts).toEqual(['11.2 s'])
    expect(agentStatus({ ok: false, items: [{ name: '装了没', ok: true, note: '/x' },
                                           { name: '登录', ok: false, note: '没登录：在终端跑 codex login' }], at: 't' }))
      .toEqual({ word: '未登录', tone: 'bad', facts: [], hint: '没登录：在终端跑 codex login' })
    expect(agentStatus({ ok: false, items: [{ name: '装了没', ok: false, note: '找不到 codex' }], at: 't' }).word).toBe('未安装')
  })
  it('算力：本机没探过、探过带 GPU、没过带原话', () => {
    expect(computeStatus(null).word).toBe('未检查')
    expect(computeStatus({ ok: true, gpu: 'RTX 4090', items: [], at: 't' })).toEqual({ word: '就绪', tone: 'ok', facts: ['RTX 4090'] })
    expect(computeStatus({ ok: false, items: [{ name: '连接', ok: false, note: '连不上（机器关了？）' }], at: 't' }))
      .toEqual({ word: '连接失败', tone: 'bad', facts: [], hint: '连不上（机器关了？）' })
    // 算力那边记的是三元组（compute.Probe.to_dict），过了的三元组不能被当成没过
    expect(computeStatus({ ok: true, gpu: 'RTX 4090', items: [['连接', true, '1.7 s'], ['GPU', true, 'RTX 4090']], at: 't' }).tone)
      .toBe('ok')
    expect(computeStatus({ ok: false, items: [['GPU', false, '没有 GPU']], at: 't' }).word).toBe('GPU未通过')
  })
  it('家目录缩成 ~', () => {
    expect(tildify('/Users/me/coding/x')).toBe('~/coding/x')
    expect(tildify('/home/me')).toBe('~')
    expect(tildify('/opt/data')).toBe('/opt/data')
    expect(tildify('/Users/me2/.config/ai4sci')).toBe('~/.config/ai4sci')
  })
  it('版本串只留版本号', () => {
    expect(shortVersion('2.1.278 (Claude Code)')).toBe('2.1.278')
    expect(shortVersion('codex-cli 0.147.0')).toBe('0.147.0')
    expect(shortVersion('nightly')).toBe('nightly')
    expect(shortVersion(undefined)).toBe('')
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
