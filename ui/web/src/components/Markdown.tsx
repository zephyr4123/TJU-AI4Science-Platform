import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { remarkTrimAutolink } from '@/components/markdown/autolink'
import { cn } from '@/lib/utils'

const PLUGINS = [remarkGfm, remarkTrimAutolink]

/** 全页面唯一的 markdown 渲染点；排版在 index.css 的 `.prose-ai4sci`。 */
export function Markdown({ text, className }: { text: string; className?: string }) {
  return (
    <div className={cn('prose-ai4sci', className)}>
      <ReactMarkdown remarkPlugins={PLUGINS}>{text}</ReactMarkdown>
    </div>
  )
}
