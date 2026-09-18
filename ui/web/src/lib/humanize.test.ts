import { describe, expect, it } from 'vitest'

import { conclusionOf, denialSentence, stopSentence, toolSentence, wakeSentence } from './humanize'

describe('run 的句子', () => {
  it('停止原因', () => {
    expect(stopSentence('patience', false)).toBe('几轮没进步，停了')
    expect(stopSentence(null, true)).toBe('在跑')
    expect(stopSentence(null, false)).toBe('可继续')
    expect(stopSentence('weird', false)).toBe('停了：weird')
  })
  it('抽结论一节', () => {
    const doc = '# 分析\n\n## 结论\n\nbest 是第 6 轮。\n\n## 数据\n\n| a |\n'
    expect(conclusionOf(doc)).toBe('best 是第 6 轮。')
    expect(conclusionOf('没有小节')).toBe('没有小节')
  })
})

describe('工具行', () => {
  it('命令翻成动作', () => {
    expect(toolSentence('Bash', { command: '.venv/bin/ai4sci cap baseline' })).toBe('跑了基线')
    expect(toolSentence('Bash', { command: 'ai4sci cap experiment r1 --resume' })).toBe('接着跑上次没走完的实验')
    expect(toolSentence('Bash', { command: 'ai4sci show task' })).toBe('检查了需求')
    expect(toolSentence('Bash', { command: 'ai4sci show workspaces' })).toBe('查了有哪些工作区')
    expect(toolSentence('Bash', { command: 'ai4sci flow take quick-look' })).toBe('从库里取了一条流')
    expect(toolSentence('Bash', { command: 'ai4sci show flows' })).toBe('看了这个工作区里的流')
    expect(toolSentence('Bash', { command: 'ai4sci cap analysis r1 --detach' })).toBe('写了分析，放到后台跑')
    expect(toolSentence('Bash', { command: 'ls -1 task/' })).toBe('看了目录')
    expect(toolSentence('Bash', { command: 'python3 -c 1' })).toBe('运行了一条命令')
    expect(toolSentence('Read', { file_path: '/a/b/task/manifest.yaml' })).toBe('读了 task/manifest.yaml')
    expect(toolSentence('Grep', { pattern: 'a' })).toBe('搜了文件')
  })
  it('框架叫醒的那一轮一句话', () => {
    const ok = '作业 job-1（`ai4sci cap experiment demo-1 --max-iters 1`）跑完了，退出码 0：\nstop batch_exhausted\n\n看一眼结果'
    expect(wakeSentence(ok)).toBe('后台作业跑完了（跑了几轮实验）')
    expect(wakeSentence('作业 job-2（`ai4sci cap analysis r1`）没跑成，退出码 1：\nx')).toBe('后台作业没跑成（写了分析）')
    expect(wakeSentence('随便一句 `话`')).toBe('随便一句 话')
  })
  it('被拒的命令一句话', () => {
    expect(denialSentence('Permission to use Bash has been denied.')).toBe('命令不在放行范围')
    expect(denialSentence('别的原因')).toBe('别的原因')
  })
})
