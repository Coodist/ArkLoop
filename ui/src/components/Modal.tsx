import { useEffect, useRef, useState } from 'react'

interface BaseProps {
  open: boolean
  title: string
  onCancel: () => void
}

interface PromptDialogProps extends BaseProps {
  placeholder?: string
  defaultValue?: string
  confirmLabel?: string
  cancelLabel?: string
  onConfirm: (value: string) => void
}

/** Centered prompt modal styled to match the rest of the app. */
export function PromptDialog({
  open,
  title,
  placeholder,
  defaultValue = '',
  confirmLabel = '确定',
  cancelLabel = '取消',
  onConfirm,
  onCancel,
}: PromptDialogProps) {
  const [value, setValue] = useState(defaultValue)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      setValue(defaultValue)
      requestAnimationFrame(() => inputRef.current?.focus())
    }
  }, [open, defaultValue])

  if (!open) return null

  const submit = () => {
    const trimmed = value.trim()
    if (!trimmed) return
    onConfirm(trimmed)
  }

  return (
    <div
      className="fixed inset-0 z-[9500] flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.6)' }}
      onMouseDown={onCancel}
    >
      <div
        className="w-80 rounded-lg border border-border-panel bg-panel shadow-2xl p-5 flex flex-col gap-4"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="text-text-primary text-sm font-medium">{title}</div>
        <input
          ref={inputRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') submit()
            if (e.key === 'Escape') onCancel()
          }}
          placeholder={placeholder}
          className="w-full bg-[#0B0F13] border border-border-panel rounded px-3 py-1.5 text-sm text-text-primary outline-none focus:border-accent-blue/60"
        />
        <div className="flex gap-2 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-1.5 rounded text-sm text-text-muted border border-border-panel hover:border-accent-red/50 hover:text-accent-red transition-colors"
          >
            {cancelLabel}
          </button>
          <button
            onClick={submit}
            disabled={!value.trim()}
            className="px-4 py-1.5 rounded text-sm text-white font-medium bg-accent-blue/80 hover:bg-accent-blue disabled:opacity-40 transition-colors"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

interface ConfirmDialogProps extends BaseProps {
  message: string
  confirmLabel?: string
  cancelLabel?: string
  destructive?: boolean
  onConfirm: () => void
}

/** Centered confirmation modal styled to match the app. */
export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = '确定',
  cancelLabel = '取消',
  destructive = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null
  return (
    <div
      className="fixed inset-0 z-[9500] flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.6)' }}
      onMouseDown={onCancel}
    >
      <div
        className="w-80 rounded-lg border border-border-panel bg-panel shadow-2xl p-5 flex flex-col gap-4"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="text-text-primary text-sm font-medium">{title}</div>
        <div className="text-xs text-text-muted leading-relaxed">{message}</div>
        <div className="flex gap-2 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-1.5 rounded text-sm text-text-muted border border-border-panel hover:border-accent-blue/50 hover:text-text-primary transition-colors"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            className={[
              'px-4 py-1.5 rounded text-sm font-medium text-white transition-colors',
              destructive
                ? 'bg-accent-red/80 hover:bg-accent-red'
                : 'bg-accent-blue/80 hover:bg-accent-blue',
            ].join(' ')}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
