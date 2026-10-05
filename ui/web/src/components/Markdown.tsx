import { memo, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { remarkTrimAutolink } from '@/components/markdown/autolink'
import { type FileAt, FileLinks, Link } from '@/components/markdown/links'
import { cn } from '@/lib/utils'

const PLUGINS = [remarkGfm, remarkTrimAutolink]
const COMPONENTS = { a: ({ href = '', children }: { href?: string; children?: ReactNode }) => <Link href={href}>{children}</Link> }

interface Props { text: string; className?: string; at?: FileAt }

/** 全页面唯一的 markdown 渲染点；排版在 index.css 的 `.prose-ai4sci`，链接怎么开在 `markdown/links.tsx`。
 *  `at`：渲染的是工作区里的一份文件时给，文件里的相对链接按它解开。
 *  字没变就不重新解析：有作业在跑时看板每 10 秒重拉、整块重渲染，需求这类没变的字不该跟着再解析一遍（外层 #242）；`at` 按值比 */
export const Markdown = memo(function Markdown({ text, className, at }: Props) {
  const body = (
    <div className={cn('prose-ai4sci', className)}>
      <ReactMarkdown remarkPlugins={PLUGINS} components={COMPONENTS}>{text}</ReactMarkdown>
    </div>
  )
  return at ? <FileLinks at={at}>{body}</FileLinks> : body
}, (a: Props, b: Props) => a.text === b.text && a.className === b.className && a.at?.ws === b.at?.ws && a.at?.path === b.at?.path)
