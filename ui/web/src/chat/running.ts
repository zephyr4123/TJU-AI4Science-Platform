// 对话底部那条「运行中」（外层 #243）的数据：整个项目里在跑的作业。项目那一整份（`GET /projects/<p>`）的每个工作区一行
// 已经带着在跑的作业，这里只摊平、排序。整个项目而不只是这段对话起的：研究者担心的是「有没有东西在跑」，不管是谁起的。纯函数，有单测。
import type { Job, ProjectDetail } from '@/api/types'

export interface RunningJob extends Job {
  workspace: string
  workspaceTitle: string
}

export function runningJobs(project: ProjectDetail | null): RunningJob[] {
  if (!project) return []
  return project.workspaces
    .flatMap((w) => w.jobs.filter((j) => j.effective_status === 'running').map((j) => ({ ...j, workspace: w.id, workspaceTitle: w.title })))
    .sort((a, b) => a.started_at.localeCompare(b.started_at))
}
