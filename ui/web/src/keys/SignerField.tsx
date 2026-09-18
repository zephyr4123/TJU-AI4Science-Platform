import { Input } from '@/components/ui/input'

export function SignerField({ value, onChange, id }: { value: string;
                                                       onChange: (v: string) => void; id: string }) {
  return (
    <div className="flex items-center gap-2">
      <label htmlFor={id} className="shrink-0 text-sm text-muted-foreground">署名</label>
      <Input id={id} value={value} onChange={(event) => onChange(event.target.value)}
             placeholder="你的名字" className="h-8 max-w-48" autoComplete="name" />
    </div>
  )
}
