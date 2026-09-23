// 对话入口还没开口时的那一屏（外层 #139，主人 2026-09-23：logo 居中、字在下，别平淡地左对齐）：平台的标在正中，底下一句宋体标题、
// 一行小字。两处共用：工作区页与编辑台那块板的欢迎屏（ChatView）、开了一段还没说话的对话正文（Transcript）；项目页正中间那一列
// 是标压在项目名上面（ProjectPage），同一种排法。标题逐词浮现（BlurText），减少动效直接出现。
import { useReducedMotion } from 'motion/react'

import { ErrorNote } from '@/components/bits'
import BlurText from '@/components/BlurText'
import { Logo } from '@/components/Logo'
import { cn } from '@/lib/utils'

export interface WelcomeCopy { headline: string; body: string }

/** 两位助理还没开口时说的话（主人 2026-09-23：别只放一个词，说成一句「你想做什么，我来帮你」）：研究助理在项目里，流程助理在编辑台 */
export const WELCOME = {
  research: { headline: '想研究什么？我来帮你。', body: '说说问题、手里的材料、怎么算做得好。' },
  studio: { headline: '想做一条什么流程？我来帮你。', body: '说说要经过哪些阶段、用哪些能力、哪里要人确认。' },
} as const satisfies Record<string, WelcomeCopy>

const TITLE = 'font-serif text-[1.75rem] leading-[1.25] font-semibold tracking-tight text-balance'

export function Welcome({ copy, error, className }: { copy: WelcomeCopy; error?: string | null; className?: string }) {
  const still = useReducedMotion()
  return (
    <div className={cn('flex flex-col items-center text-center', className)}>
      <Logo className="size-12 text-primary" />
      {still
        ? <h2 className={cn(TITLE, 'mt-6')}>{copy.headline}</h2>
        : <BlurText text={copy.headline} delay={50} animateBy="words" direction="top" className={cn(TITLE, 'mt-6 justify-center')} />}
      <p className="t-body mt-3 text-muted-foreground">{copy.body}</p>
      {error && <ErrorNote text={error} className="mt-6 text-left" />}
    </div>
  )
}
