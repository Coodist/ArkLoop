import { useEffect, useRef, useState } from 'react'

interface SaveDialogProps {
  defaultName: string   // without .json
  onSave: (name: string) => void
  onDelete: () => void
  onDismiss: () => void
}

export function SaveDialog({ defaultName, onSave, onDelete, onDismiss }: SaveDialogProps) {
  const [name, setName] = useState(defaultName)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
    inputRef.current?.select()
  }, [])

  const handleSave = () => {
    const trimmed = name.trim()
    if (!trimmed) return
    onSave(trimmed)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSave()
    if (e.key === 'Escape') onDismiss()
  }

  return (
    // Overlay
    <div
      className="fixed inset-0 z-[9000] flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.6)' }}
      onMouseDown={onDismiss}
    >
      {/* Dialog box */}
      <div
        className="w-80 rounded-lg border border-border-panel bg-panel shadow-2xl p-5 flex flex-col gap-4"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="text-text-primary text-sm font-medium">保存录制</div>

        <div className="flex flex-col gap-1.5">
          <label className="text-xs text-text-dim">轴名称</label>
          <input
            ref={inputRef}
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={handleKeyDown}
            className="w-full bg-[#0B0F13] border border-border-panel rounded px-3 py-1.5 text-sm text-text-primary outline-none focus:border-accent-blue/60"
          />
        </div>

        <div className="flex gap-2">
          {/* Save — blue fill, primary action */}
          <button
            onClick={handleSave}
            disabled={!name.trim()}
            className="flex-1 py-1.5 rounded text-sm text-white font-medium bg-accent-blue/80 hover:bg-accent-blue disabled:opacity-40 transition-colors"
          >
            保存
          </button>
          {/* Delete — outlined, secondary/destructive */}
          <button
            onClick={onDelete}
            className="px-4 py-1.5 rounded text-sm text-text-muted border border-border-panel hover:border-accent-red/50 hover:text-accent-red transition-colors"
          >
            删除
          </button>
        </div>
      </div>
    </div>
  )
}
