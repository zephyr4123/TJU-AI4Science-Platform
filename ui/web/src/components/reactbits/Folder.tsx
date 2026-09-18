// 一只文件夹，从 reactbits 的 Folder 捞来改装（MIT，https://reactbits.dev/components/folder）：
// 工作区就是一个文件夹——整个打包能交给同事。改装点：颜色走 tokens 由调用方给；开合由调用方控制
// （名字一打进来它就打开），不靠点击；文件夹的标签上写工作区名；三张纸是真内容不是空白。
// 尺寸按 CSS 变量 --folder-w 缩放，动效尊重 prefers-reduced-motion（index.css 里统一退化）。
import { type CSSProperties, type ReactNode } from 'react'

import { cn } from '@/lib/utils'

// 打开时三张纸的落点：左、右、正上；x 里含着 -50% 的居中量，纸不会飞出文件夹的地盘太远
const OPEN_TRANSFORM = [
  'translate(-112%, -58%) rotate(-12deg)',
  'translate(14%, -56%) rotate(12deg)',
  'translate(-50%, -104%) rotate(3deg)',
]

/** 把 hex 压暗一点，给文件夹的背板。 */
function darken(hex: string, amount: number): string {
  const raw = hex.replace('#', '')
  const full = raw.length === 3 ? raw.split('').map((c) => c + c).join('') : raw
  const num = parseInt(full.slice(0, 6), 16)
  if (Number.isNaN(num)) return hex
  const ch = (v: number) => Math.max(0, Math.min(255, Math.floor(v * (1 - amount))))
  const r = ch((num >> 16) & 0xff), g = ch((num >> 8) & 0xff), b = ch(num & 0xff)
  return `#${((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1)}`
}

export function Folder({ color, label, open, papers, width = 220, className }: {
  color: string
  /** 文件夹标签上的字：工作区名 */
  label: string
  open: boolean
  /** 最多三张纸，每张是一小段内容 */
  papers: ReactNode[]
  width?: number
  className?: string
}) {
  const sheets = papers.slice(0, 3)
  const height = Math.round(width * 0.8)
  const style = { '--folder': color, '--folder-back': darken(color, 0.1) } as CSSProperties
  return (
    <div className={cn('relative', className)} style={{ ...style, width, height: height + 24 }}>
      <div
        className="group relative mt-6 transition-transform duration-300 ease-out"
        style={{ width, height, transform: open ? 'translateY(-6px)' : undefined,
                 filter: 'drop-shadow(0 18px 28px color-mix(in oklab, var(--folder) 28%, transparent))' }}
        aria-hidden
      >
        {/* 背板与标签 */}
        <div className="absolute inset-0 rounded-tr-[14px] rounded-b-[14px]" style={{ backgroundColor: 'var(--folder-back)' }} />
        <div
          className="absolute bottom-full left-0 flex h-7 max-w-[70%] items-center rounded-t-[8px] px-3 font-mono text-[0.8125rem] text-white/90"
          style={{ backgroundColor: 'var(--folder-back)' }}
        >
          <span className="truncate">{label || 'workspaces/…'}</span>
        </div>
        {/* 三张纸 */}
        {sheets.map((sheet, i) => {
          const size = ['w-[72%] h-[82%]', 'w-[82%] h-[80%]', 'w-[92%] h-[78%]'][i]
          return (
            <div
              key={i}
              className={cn('absolute bottom-[10%] left-1/2 z-20 overflow-hidden rounded-[10px] border border-border bg-card',
                            'px-3 py-2.5 text-left transition-all duration-500 ease-out', size,
                            !open && '-translate-x-1/2 translate-y-[10%] group-hover:translate-y-[-6%]')}
              style={open ? { transform: OPEN_TRANSFORM[i] } : undefined}
            >
              {sheet}
            </div>
          )
        })}
        {/* 两片折起来的前面板 */}
        {[15, -15].map((skew) => (
          <div
            key={skew}
            className="absolute inset-0 z-30 origin-bottom rounded-[6px_14px_14px_14px] transition-transform duration-500 ease-out"
            style={{ background: `linear-gradient(${skew > 0 ? '160deg' : '200deg'}, color-mix(in oklab, var(--folder) 86%, white) 0%, var(--folder) 55%)`,
                     transform: open ? `skew(${skew}deg) scaleY(0.62)` : undefined }}
          />
        ))}
      </div>
    </div>
  )
}
