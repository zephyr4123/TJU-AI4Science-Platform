// 删除项目的「…」（外层 #250）：首页清单每行一枚（主人 2026-10-06：非得点进项目才能删不对），项目页右上角一枚。
// 里面只有一件事：删整个项目——全部工作区、对话及其会话、机器上的镜像一起删，按住一秒才算数。
import { DotsThree, Trash } from '@phosphor-icons/react'
import { useState } from 'react'

import { ErrorNote } from '@/components/bits'
import HoldButton from '@/components/reactbits/HoldButton'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'

export function ProjectMenu({ title, onRemove, className }: {
  title: string
  /** 删完由调用方收尾（刷新清单、回首页）；失败抛出来，写在菜单里 */
  onRemove: () => Promise<void>
  /** 键的样子由所在的地方定（首页那枚鼠标进行才出现） */
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)
  const remove = () => {
    setFailed(null)
    onRemove().then(() => setOpen(false)).catch((exc: unknown) => setFailed(exc instanceof Error ? exc.message : String(exc)))
  }
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={`删除项目「${title}」`} className={cn('rounded-full', className)}>
          <DotsThree weight="bold" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[18rem] space-y-3 p-4">
        <p className="text-[0.875rem] font-medium">删除项目</p>
        <p className="line-clamp-2 text-[0.8125rem]">{title}</p>
        <p className="text-[0.75rem] text-muted-foreground">全部工作区、对话及其会话、机器上的镜像一起删，回不来。</p>
        <div className="flex items-center gap-3">
          <HoldButton onHold={remove} doneLabel="已删除"><Trash className="size-3.5" />删除</HoldButton>
        </div>
        {failed && <ErrorNote text={failed} />}
      </PopoverContent>
    </Popover>
  )
}
