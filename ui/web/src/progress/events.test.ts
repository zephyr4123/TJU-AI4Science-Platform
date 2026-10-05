import { describe, expect, it } from 'vitest'

import { parseEvents } from './events'

describe('parseEvents', () => {
  it('一行一个事件；正写到一半的最后一行、没有 at 的行、空行都跳过', () => {
    const text = '{"at": "t1", "step": "seeds"}\n\n{"step": "x"}\n{"at": "t2", "step": "gather", "done": true}\n{"at": "t3", "st'
    expect(parseEvents(text)).toEqual([{ at: 't1', step: 'seeds' }, { at: 't2', step: 'gather', done: true }])
  })
})
