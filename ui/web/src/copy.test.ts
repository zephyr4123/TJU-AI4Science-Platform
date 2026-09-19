// 页面文案的机器判据（纲领 P-21，外层 #112）：扫 src 下所有会上屏的源码，去掉注释后
// 1. 不许出现禁用词——口语、问句式标签、借来的量词、比喻、词表里被替掉的旧词（「工作流」→「流程」）；
// 2. `font-mono` 只许出现在文件镜头与代码块：文件名、命令、diff 是内容不是字段，别的地方等宽字就是机器的名字上了屏。
// 后端那份禁用词在 framework/contracts/capability.py 的 BANNED_WORDS，两边各守各的门，词表在外层 workflow §5。
/// <reference types="node" />
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

import { describe, expect, it } from 'vitest'

const SRC = new URL('.', import.meta.url).pathname
const BANNED = ['签了', '没成', '在跑', '续命', '这包', '越界', '干什么', '收尸', '按钮', '房间', '裁判',
                '一颗', '几颗', '每颗', '那颗', '哪颗', '工作流']
/** 等宽字只许在这几处：文件镜头（路径与代码是内容）、对话里的工具调用（命令原样）、需求的行级 diff、产出目录的文件清单 */
const MONO_ALLOWED = new Set(['files/Files.tsx', 'chat/TurnView.tsx', 'board/Requirement.tsx', 'board/OutputSheet.tsx'])

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name: string) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return sources(path)
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : []
  })
}

/** 去掉块注释与行注释：注释里可以引主人的原话（「看不出是干什么的」），上屏的字才算 */
function withoutComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:'"`])\/\/.*$/gm, '$1')
}

const files = sources(SRC).map((path) => ({ path: relative(SRC, path), lines: withoutComments(readFileSync(path, 'utf8')).split('\n') }))

describe('页面文案（P-21）', () => {
  it('扫到了页面的源码（不然下面两条是空转）', () => {
    expect(files.length).toBeGreaterThan(40)
    expect(files.some(({ path }) => path === 'App.tsx')).toBe(true)
    expect(withoutComments("a // 注释里的「签了」\nb /* 「没成」 */ c")).toBe('a \nb  c')
  })
  it('源码里没有禁用词', () => {
    const hits = files.flatMap(({ path, lines }) => lines.flatMap((line, i) =>
      BANNED.filter((word) => line.includes(word)).map((word) => `${path}:${i + 1} 「${word}」`)))
    expect(hits).toEqual([])
  })
  it('等宽字只在文件镜头与代码块', () => {
    const hits = files.filter(({ path }) => !MONO_ALLOWED.has(path))
      .flatMap(({ path, lines }) => lines.flatMap((line, i) => (line.includes('font-mono') ? [`${path}:${i + 1}`] : [])))
    expect(hits).toEqual([])
  })
})
