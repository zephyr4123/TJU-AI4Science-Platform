// 铺满一块面板的画面：图铺底、纱幕压到字能读（外层 #82 #84，主人：别纯白、别方格纸，用轻的风景图）。
// side 是欢迎屏那种：左边压成纸色给字站、右边留给画面；mist 是对话正文与看板底下那种：整块压到只剩一点氛围。横幅用 Band，这个铺整块。
import type { Picture } from '@/assets'
import { Photo } from '@/components/Photo'
import { cn } from '@/lib/utils'

interface Props {
  picture: Picture
  veil: 'side' | 'mist'
  className?: string
}

export function Scene({ picture, veil, className }: Props) {
  return (
    <div aria-hidden="true" className={cn('pointer-events-none absolute inset-0 overflow-hidden', className)}>
      <Photo picture={picture} />
      <div className={cn('absolute inset-0', veil === 'side' ? 'veil' : 'veil-mist')} />
    </div>
  )
}
