import { describe, expect, it } from 'vitest'

import { chipName } from './CallChip'

describe('CallChip 的读屏名（WCAG 2.5.3）', () => {
  it('一直带着看得见的那个字，后面跟此刻怎样', () => {
    expect(chipName('试通', 'idle')).toBe('试通')
    expect(chipName('试通', 'running')).toBe('试通：进行中')
    expect(chipName('试通', 'error')).toBe('试通：没过，再试')
    expect(chipName('检查', 'done')).toBe('检查：过了')
  })
})
