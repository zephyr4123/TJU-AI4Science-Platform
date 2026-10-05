// 能力边跑边写的进度（外层 #242）：产出目录下的 `progress.jsonl`，一行一个事件，是能力的 Python 程序在它本来就打日志的
// 地方顺手追加的（`framework/files.py::append_event`）。每行都带 `at`，其余字段归各个能力——所以这里只管读：取文件、
// 一行一行解开；事件长什么样、怎么画，在各个能力自己的面板里（search.ts / read.ts）。
// 读的时候能力可能正写到一半：最后一行解不开就丢掉，下一次再读到它。
import { useEffect, useState } from 'react'

import { ApiError, type WorkspaceClient } from '@/api/client'

export const PROGRESS_FILE = 'progress.jsonl'
/** 作业在跑时多久重读一次进度 */
const POLL_MS = 2000

/** 面板上一步（一个方块）的状态：没到、运行中、完成、失败（作业停在这一步）、跳过（跑完了也没走到） */
export type Phase = 'pending' | 'running' | 'done' | 'failed' | 'skipped'

export interface ProgressEvent {
  at: string
  [field: string]: unknown
}

/** 一行一个 JSON；解不开的行（正写到一半的最后一行）跳过，不报错 */
export function parseEvents(text: string): ProgressEvent[] {
  const events: ProgressEvent[] = []
  for (const line of text.split('\n')) {
    if (!line.trim()) continue
    try {
      const row: unknown = JSON.parse(line)
      if (row && typeof row === 'object' && typeof (row as { at?: unknown }).at === 'string') events.push(row as ProgressEvent)
    } catch {
      // 写到一半的那一行：下一次读到完整的
    }
  }
  return events
}

/** 一次产出的进度事件。`live`（产出还在运行中）时每两秒重读；停下来再读最后一次。
 *  文件还没写出来（刚开工）或这次产出早于进度文件（旧产出）都当没有事件：`[]`。 */
export function useProgress(workspace: WorkspaceClient, oid: string, live: boolean): { events: ProgressEvent[] | null; error: string | null } {
  const [state, setState] = useState<{ key: string; events: ProgressEvent[] | null; error: string | null }>(
    { key: '', events: null, error: null })
  const key = `${workspace.key}:${oid}`
  useEffect(() => {
    let gone = false
    const load = () => {
      workspace.file(`${oid}/${PROGRESS_FILE}`)
        .then((file) => { if (!gone) setState({ key, events: parseEvents(file.text ?? ''), error: null }) })
        .catch((exc: unknown) => {
          if (gone) return
          if (exc instanceof ApiError && exc.status === 404) setState({ key, events: [], error: null })
          else setState((prev) => ({ key, events: prev.key === key ? prev.events : null, error: exc instanceof Error ? exc.message : String(exc) }))
        })
    }
    load()
    if (!live) return () => { gone = true }
    const timer = setInterval(load, POLL_MS)
    return () => { gone = true; clearInterval(timer) }
  }, [workspace, oid, key, live])
  return state.key === key ? { events: state.events, error: state.error } : { events: null, error: null }
}
