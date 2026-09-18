// 全铺的动态背景，只给「新建工作区」那一屏（docs/DESIGN.md「素材」）：浅色 / 深色各一段无缝循环、无声。
// 系统要求减少动效或省流量时不拉视频，只给首帧海报；视频加载失败也停在海报上。上面压一层纱幕，字才压得住。
import { useReducedMotion } from 'motion/react'
import { useState } from 'react'

import type { Clip } from '@/assets'
import { useDark } from '@/lib/useMediaQuery'
import { cn } from '@/lib/utils'

interface Props {
  clip: { light: Clip; dark: Clip }
  className?: string
}

export function Backdrop({ clip, className }: Props) {
  const dark = useDark()
  const still = useReducedMotion()
  // 哪一段已经真的在放：换深浅色会换片子，新片子放起来之前先露海报
  const [playing, setPlaying] = useState<string | null>(null)
  const c = dark ? clip.dark : clip.light
  const saveData = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData === true
  const withVideo = !still && !saveData

  return (
    <div className={cn('pointer-events-none absolute inset-0 overflow-hidden', className)} aria-hidden="true">
      <img src={c.poster} alt="" decoding="async" className="absolute inset-0 size-full object-cover" />
      {withVideo && (
        <video
          key={c.video} src={c.video} poster={c.poster} autoPlay muted loop playsInline preload="auto"
          onPlaying={() => setPlaying(c.video)}
          className={cn('absolute inset-0 size-full object-cover transition-opacity duration-500',
                        playing === c.video ? 'opacity-100' : 'opacity-0')}
        />
      )}
      <div className="veil absolute inset-0" />
    </div>
  )
}
