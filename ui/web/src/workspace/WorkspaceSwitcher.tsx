// 顶栏的工作区切换：一个下拉，末项「新建工作区」。工作区是页面认路的第一件事（纲领 P-15）。
import { Plus } from 'lucide-react'

import type { WorkspaceSummary } from '@/api/types'
import { Button } from '@/components/ui/button'

interface Props {
  workspaces: WorkspaceSummary[] | null
  selected: string | null
  onPick: (id: string) => void
  onNew: () => void
}

export function WorkspaceSwitcher({ workspaces, selected, onPick, onNew }: Props) {
  const ordered = workspaces ? [...workspaces].sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? '')) : []
  return (
    <div className="flex min-w-0 items-center gap-1.5">
      <select
        aria-label="工作区" value={selected ?? ''} disabled={ordered.length === 0}
        onChange={(e) => onPick(e.target.value)}
        className="h-8 max-w-[18rem] min-w-0 truncate rounded-md border bg-card px-2 text-[0.875rem] font-medium disabled:text-muted-foreground"
      >
        {ordered.length === 0 && <option value="">还没有工作区</option>}
        {ordered.map((w) => <option key={w.id} value={w.id}>{w.title}</option>)}
      </select>
      <Button variant="ghost" size="icon-sm" onClick={onNew} aria-label="新建工作区" title="新建工作区">
        <Plus />
      </Button>
    </div>
  )
}
