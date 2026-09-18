// 页眉右边的深浅色开关（外层 #91）：太阳、开关、月亮三样一行，哪边亮着就是哪边；拨了记在本机，没拨过跟系统。
import { MoonStars, Sun } from '@phosphor-icons/react'

import SquishSwitch from '@/components/reactbits/SquishSwitch'
import { useTheme } from '@/lib/theme'
import { cn } from '@/lib/utils'

export function ThemeToggle({ className }: { className?: string }) {
  const { dark, setDark } = useTheme()
  return (
    <span className={cn('inline-flex items-center gap-2', className)}>
      <Sun aria-hidden="true" className={cn('size-4', dark ? 'text-muted-foreground/60' : 'text-foreground')} />
      <SquishSwitch checked={dark} onChange={setDark} ariaLabel="深色模式" />
      <MoonStars aria-hidden="true" className={cn('size-4', dark ? 'text-foreground' : 'text-muted-foreground/60')} />
    </span>
  )
}
