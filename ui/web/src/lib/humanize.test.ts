import { describe, expect, it } from 'vitest'

import { conclusionOf, denialSentence, outputWord, requirementWord, stageSentence, stopSentence, wakeSentence } from './humanize'

describe('需求与产出的句子', () => {
  it('需求状态', () => {
    expect(requirementWord({ confirmed: false, version: null, by: null, at: null, dirty: false })).toBe('需求未确认')
    expect(requirementWord({ confirmed: true, version: 2, by: 'a', at: 't', dirty: false })).toBe('需求 v2')
    expect(requirementWord({ confirmed: true, version: 2, by: 'a', at: 't', dirty: true })).toBe('需求 v2 · 有改动')
  })
  it('工作区走到哪', () => {
    const base = { id: 'w', title: 'w', root: '/w', running: 0, counts: { design: 0 } }
    expect(stageSentence({ ...base, requirement: { confirmed: false, version: null, by: null, at: null, dirty: false } })).toBe('需求未确认')
    const ok = { confirmed: true, version: 1, by: 'a', at: 't', dirty: false }
    expect(stageSentence({ ...base, requirement: ok })).toBeNull()
    expect(stageSentence({ ...base, requirement: ok, counts: { design: 1, experiment: 2 } })).toBeNull()
    expect(stageSentence({ ...base, requirement: ok, running: 1 })).toBe('运行中 1')
  })
  it('一次产出', () => {
    const signed = { by: 'a', signed_at: 't', sha256: 'x', note: '', stale: false }
    expect(outputWord({ status: 'running', signed: null })).toBe('运行中')
    expect(outputWord({ status: 'failed', signed: null })).toBe('失败')
    expect(outputWord({ status: 'ok', signed: null })).toBe('完成')
    expect(outputWord({ status: 'ok', signed })).toBe('已确认')
    expect(outputWord({ status: 'ok', signed: { ...signed, stale: true } })).toBe('已确认 · 之后有改动')
  })
})

describe('实验的句子', () => {
  it('停止原因', () => {
    expect(stopSentence('patience', false)).toBe('多轮无进步，已停止')
    expect(stopSentence(null, true)).toBe('运行中')
    expect(stopSentence(null, false)).toBe('可继续')
    expect(stopSentence('weird', false)).toBe('已停止：weird')
  })
  it('抽结论一节', () => {
    const doc = '# 分析\n\n## 结论\n\nbest 是第 6 轮。\n\n## 数据\n\n| a |\n'
    expect(conclusionOf(doc)).toBe('best 是第 6 轮。')
    expect(conclusionOf('没有小节')).toBe('没有小节')
  })
})

describe('对话里的句子', () => {
  it('框架叫醒的那一轮：后台作业完成 / 失败 + 那条命令', () => {
    const ok = '作业 job-1（`ai4sci cap auto-research --max-iters 1`）跑完了，退出码 0：\nstop batch_exhausted\n\n看一眼结果'
    expect(wakeSentence(ok)).toBe('后台作业完成：ai4sci cap auto-research --max-iters 1')
    expect(wakeSentence('作业 job-2（`ai4sci cap analysis --from experiment/1`）没跑成，退出码 1：\nx')).toBe('后台作业失败：ai4sci cap analysis --from experiment/1')
    expect(wakeSentence('随便一句 `话`')).toBe('随便一句 话')
  })
  it('被拒的命令一句话', () => {
    expect(denialSentence('Permission to use Bash has been denied.')).toBe('命令不在放行范围')
    expect(denialSentence('别的原因')).toBe('别的原因')
  })
})
