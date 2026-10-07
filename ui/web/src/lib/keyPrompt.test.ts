import { describe, expect, it } from 'vitest'

import type { AssistantStatus } from '@/api/types'

import { keyPromptStep, skipMark } from './keyPrompt'

const AT = '2026-10-07T10:00:00+08:00'
const LATER = '2026-10-07T11:30:00+08:00'
const of = (state: AssistantStatus['state'], checked_at: string | null = AT): AssistantStatus =>
  ({ agent: 'claude_code', provider: 'deepseek', state, reason: '一句原因', checked_at })

describe('「助理还不能说话」什么时候弹（外层 #282）', () => {
  it('缺 key、没跳过这一次：弹', () => {
    expect(keyPromptStep(of('needs_key'), null, false)).toBe('ask')
    expect(keyPromptStep(of('needs_key'), null, true)).toBe('ask')
  })
  it('跳过的就是这一次自检：不弹；下一次自检结果出来（时间变了）再弹', () => {
    expect(keyPromptStep(of('needs_key'), AT, false)).toBe('none')
    expect(keyPromptStep(of('needs_key', LATER), AT, false)).toBe('ask')
  })
  it('还没自检过就缺 key：跳过记空串，自检一次有了时间才再弹', () => {
    expect(skipMark(of('needs_key', null))).toBe('')
    expect(keyPromptStep(of('needs_key', null), '', false)).toBe('none')
    expect(keyPromptStep(of('needs_key', null), null, false)).toBe('ask')
    expect(keyPromptStep(of('needs_key'), '', false)).toBe('ask')
    expect(skipMark(of('needs_key'))).toBe(AT)
  })
  it('说不了话（余额不足、连不上）与就绪都不弹，跳没跳过都一样', () => {
    for (const skipped of [null, AT, '']) {
      expect(keyPromptStep(of('cannot_talk'), skipped, false)).toBe('none')
      expect(keyPromptStep(of('ready'), skipped, false)).toBe('none')
    }
  })
  it('没检查过：一次页面加载后台探一次，探过就不再探', () => {
    expect(keyPromptStep(of('unchecked', null), null, false)).toBe('probe')
    expect(keyPromptStep(of('unchecked', null), '', false)).toBe('probe')
    expect(keyPromptStep(of('unchecked', null), null, true)).toBe('none')
  })
  it('设置还没取到（或服务没给这一段）：什么都不做', () => {
    expect(keyPromptStep(null, null, false)).toBe('none')
  })
})
