import type { ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { remarkTrimAutolink } from '@/components/markdown/autolink'
import { type FileAt, FileLinks, Link } from '@/components/markdown/links'
import { cn } from '@/lib/utils'

const PLUGINS = [remarkGfm, remarkTrimAutolink]
const COMPONENTS = { a: ({ href = '', children }: { href?: string; children?: ReactNode }) => <Link href={href}>{children}</Link> }

/** 全页面唯一的 markdown 渲染点；排版在 index.css 的 `.prose-ai4sci`，链接怎么开在 `markdown/links.tsx`。
 *  `at`：渲染的是工作区里的一份文件时给，文件里的相对链接按它解开 */
export function Markdown({ text, className, at }: { text: string; className?: string; at?: FileAt }) {
  const body = (
    <div className={cn('prose-ai4sci', className)}>
      <ReactMarkdown remarkPlugins={PLUGINS} components={COMPONENTS}>{text}</ReactMarkdown>
    </div>
  )
  return at ? <FileLinks at={at}>{body}</FileLinks> : body
}
