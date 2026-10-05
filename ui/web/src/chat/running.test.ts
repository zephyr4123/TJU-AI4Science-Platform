import { describe, expect, it } from 'vitest'

import type { Job, ProjectDetail, WorkspaceRow } from '@/api/types'

import { runningJobs } from './running'

const job = (id: string, started: string, status: Job['effective_status'] = 'running', output: string | null = 'literature/1'): Job => ({
  job_id: id, cap: 'literature-search', stage: 'literature', argv: [], pid: 1, started_at: started, status: 'running',
  effective_status: status, finished_at: null, exit_code: null, result: '', chat_id: null, log: '', flow: null, output,
})
const row = (id: string, title: string, jobs: Job[]): WorkspaceRow => ({
  id, title, root: '', counts: {}, running: jobs.length, flows: [], jobs,
  requirement: { confirmed: true, version: 1, dirty: false } as WorkspaceRow['requirement'],
})
const project = (rows: WorkspaceRow[]): ProjectDetail => ({ id: 'p', title: 'P', goal: '', root: '', created_at: '', running: 0, text: '', workspaces: rows })

describe('runningJobs', () => {
  it('全项目在跑的作业，按开始的先后；记下在哪个工作区', () => {
    const jobs = runningJobs(project([
      row('a', '甲', [job('j2', '2026-10-05T05:30:00+00:00')]),
      row('b', '乙', [job('j1', '2026-10-05T05:20:00+00:00'), job('j3', '2026-10-05T05:40:00+00:00', 'lost')]),
    ]))
    expect(jobs.map((j) => [j.job_id, j.workspace, j.workspaceTitle])).toEqual([['j1', 'b', '乙'], ['j2', 'a', '甲']])
  })

  it('没有项目那一整份、没有在跑的：空', () => {
    expect(runningJobs(null)).toEqual([])
    expect(runningJobs(project([row('a', '甲', [])]))).toEqual([])
  })
})
