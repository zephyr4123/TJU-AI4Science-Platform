import type { ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { remarkTrimAutolink } from '@/components/markdown/autolink'
import { Link } from '@/components/markdown/links'
import { cn } from '@/lib/utils'

const PLUGINS = [remarkGfm, remarkTrimAutolink]
const COMPONENTS = { a: ({ href = '', children }: { href?: string; children?: ReactNode }) => <Link href={href}>{children}</Link> }

/** 全页面唯一的 markdown 渲染点；排版在 index.css 的 `.prose-ai4sci`，链接怎么开在 `markdown/links.tsx`。 */
export function Markdown({ text, className }: { text: string; className?: string }) {
  return (
    <div className={cn('prose-ai4sci', className)}>
      <ReactMarkdown remarkPlugins={PLUGINS} components={COMPONENTS}>{text}</ReactMarkdown>
    </div>
  )
}
