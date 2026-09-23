// 铺底的一张图：已经在浏览器里的（预热过、显过）直接就在；第一次到之前是页面底色，到了淡入。Scene 与 Band 都用它。
import { useState } from 'react'

import type { Picture } from '@/assets'
import { ready } from '@/lib/pictures'
import { cn } from '@/lib/utils'

export function Photo({ picture, className }: { picture: Picture; className?: string }) {
  const [shown, setShown] = useState(() => ready.has(picture.src))
  const arrive = () => { ready.add(picture.src); if (!shown) setShown(true) }
  return (
    <img src={picture.src} srcSet={picture.srcSet} sizes="100vw" alt="" decoding="async" aria-hidden="true"
         ref={(el) => { if (el?.complete && el.naturalWidth > 0) arrive() }}
         onLoad={arrive}
         className={cn('pointer-events-none absolute inset-0 size-full object-cover transition-opacity duration-300 ease-out motion-reduce:transition-none',
                       shown ? 'opacity-100' : 'opacity-0', className)} />
  )
}
