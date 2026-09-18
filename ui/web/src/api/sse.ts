// 发一轮消息、逐个事件回调。POST 的响应是 text/event-stream，浏览器原生 EventSource 只会 GET，
// 所以用 fetch 读流、eventsource-parser 切事件（分块边界落在一条事件中间是常态，别手写切分）。

import { createParser } from 'eventsource-parser'

import { ApiError, errorMessage, type Scope, scopePath } from './client'
import type { ChatEvent, Tuning } from './types'

/** 发一轮。`tuning` 是这一轮用的模型与思考深度（null 是后端缺省），服务端记进对话，之后每轮沿用。 */
export async function streamTurn(
  scope: Scope,
  chatId: string,
  text: string,
  tuning: Tuning,
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${scopePath(scope)}/chats/${encodeURIComponent(chatId)}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, ...tuning }),
    signal,
  })
  if (!res.ok) throw new ApiError(res.status, errorMessage(res.status, await res.text()))
  if (!res.body) throw new ApiError(res.status, '服务没有返回事件流')
  const parser = createParser({
    onEvent: (message) => onEvent(JSON.parse(message.data) as ChatEvent),
  })
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    parser.feed(value)
  }
}
