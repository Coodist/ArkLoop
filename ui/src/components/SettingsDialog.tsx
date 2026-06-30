import { useEffect, useState } from 'react'
import type { AppConfig } from '../hooks/useBackend'

interface SettingsDialogProps {
  open: boolean
  getConfig: () => Promise<AppConfig>
  updateConfig: (patch: Partial<AppConfig>) => Promise<boolean>
  onDismiss: () => void
}

/**
 * Settings modal. Loaded lazily when ``open`` flips to true so a slow
 * filesystem read doesn't stall app startup.
 *
 * Currently only edits the MuMu install path + instance index (the bits
 * that were hardcoded before). New fields go here as more settings move
 * out of `src/config.py`.
 */
export function SettingsDialog({ open, getConfig, updateConfig, onDismiss }: SettingsDialogProps) {
  const [path, setPath] = useState('')
  const [instance, setInstance] = useState(0)
  const [captureType, setCaptureType] = useState<string>('auto')
  const [windowName, setWindowName] = useState('MuMu模拟器12')
  const [subWindowName, setSubWindowName] = useState('MuMuPlayer')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [savedAt, setSavedAt] = useState<number | null>(null)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true)
    getConfig()
      .then((cfg) => {
        if (cancelled) return
        setPath(cfg?.mumu?.install_path ?? '')
        setInstance(typeof cfg?.mumu?.instance_index === 'number' ? cfg.mumu.instance_index : 0)
        setCaptureType(cfg?.capture_type ?? 'auto')
        setWindowName(cfg?.mumu?.window_name ?? 'MuMu模拟器12')
        setSubWindowName(cfg?.mumu?.sub_window_name ?? 'MuMuPlayer')
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [open, getConfig])

  if (!open) return null

  const handleSave = async () => {
    setSaving(true)
    try {
      const ok = await updateConfig({
        capture_type: captureType,
        mumu: {
          install_path: path.trim(),
          instance_index: Number.isFinite(instance) ? instance : 0,
          window_name: windowName.trim() || 'MuMu模拟器12',
          sub_window_name: subWindowName.trim() || 'MuMuPlayer',
        },
      })
      if (ok) setSavedAt(Date.now())
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-[9100] flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.6)' }}
      onMouseDown={onDismiss}
    >
      <div
        className="w-[460px] rounded-lg border border-border-panel bg-panel shadow-2xl p-5 flex flex-col gap-4"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="text-text-primary text-sm font-medium">设置</div>

        {loading ? (
          <div className="text-xs text-text-dim italic">读取配置中…</div>
        ) : (
          <>
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-text-dim">MuMu 模拟器安装目录</label>
              <input
                value={path}
                onChange={(e) => setPath(e.target.value)}
                placeholder={'例：D:\\Program Files\\Netease\\MuMu Player 12'}
                className="w-full bg-[#0B0F13] border border-border-panel rounded px-3 py-1.5 text-sm text-text-primary font-mono outline-none focus:border-accent-blue/60"
              />
              <div className="text-[11px] text-text-dim leading-relaxed">
                指向 MuMu Player 12 的根目录（包含 <span className="font-mono">nx_device</span> /
                <span className="font-mono"> nx_main</span> /
                <span className="font-mono"> shell</span> 子目录中的任一）。修改后**需要重启 ArkFun 才能生效**——
                MuMu DLL 句柄在首次截图时缓存。
              </div>
            </div>

            <div className="flex gap-3">
              <div className="flex flex-col gap-1.5 flex-1">
                <label className="text-xs text-text-dim">MuMu 父窗口标题</label>
                <input
                  value={windowName}
                  onChange={(e) => setWindowName(e.target.value)}
                  placeholder="MuMu模拟器12"
                  className="w-full bg-[#0B0F13] border border-border-panel rounded px-3 py-1.5 text-sm text-text-primary font-mono outline-none focus:border-accent-blue/60"
                />
              </div>
              <div className="flex flex-col gap-1.5 flex-1">
                <label className="text-xs text-text-dim">渲染子窗口标题</label>
                <input
                  value={subWindowName}
                  onChange={(e) => setSubWindowName(e.target.value)}
                  placeholder="MuMuPlayer"
                  className="w-full bg-[#0B0F13] border border-border-panel rounded px-3 py-1.5 text-sm text-text-primary font-mono outline-none focus:border-accent-blue/60"
                />
              </div>
            </div>
            <div className="text-[11px] text-text-dim leading-relaxed -mt-2">
              如果 MuMu 改名 / 多开 / 海外版导致窗口找不到，按 Win+R 输入
              <span className="font-mono"> spy++ </span>或运行下面这条命令把真实标题填进来：
              <div className="font-mono text-[10px] bg-[#0B0F13] px-2 py-1 rounded mt-1 border border-border-panel break-all">
                python -c "import win32gui; p=win32gui.FindWindow(None,'MuMu模拟器12'); c=[]; win32gui.EnumChildWindows(p, lambda h,l: l.append((h, win32gui.GetClassName(h), win32gui.GetWindowText(h))), c); [print(x) for x in c]"
              </div>
              现在只按填写的标题精确匹配，若找不到会直接报错，不再回退到类名 / 最大子窗口启发式。
            </div>

            <div className="flex gap-3">
              <div className="flex flex-col gap-1.5 flex-1">
                <label className="text-xs text-text-dim">实例索引</label>
                <input
                  type="number"
                  min={0}
                  value={instance}
                  onChange={(e) => {
                    const v = parseInt(e.target.value, 10)
                    setInstance(Number.isFinite(v) && v >= 0 ? v : 0)
                  }}
                  className="w-full bg-[#0B0F13] border border-border-panel rounded px-3 py-1.5 text-sm text-text-primary font-mono outline-none focus:border-accent-blue/60"
                />
              </div>
              <div className="flex flex-col gap-1.5 flex-1">
                <label className="text-xs text-text-dim">截图后端</label>
                <select
                  value={captureType}
                  onChange={(e) => setCaptureType(e.target.value)}
                  className="w-full bg-[#0B0F13] border border-border-panel rounded px-3 py-1.5 text-sm text-text-primary outline-none focus:border-accent-blue/60"
                >
                  <option value="auto">auto（DLL 失败回退 Win32）</option>
                  <option value="mumu">mumu（强制 DLL）</option>
                  <option value="win32">win32（强制 BitBlt）</option>
                </select>
              </div>
            </div>
          </>
        )}

        <div className="flex items-center justify-between gap-2 pt-1">
          <span className="text-xs text-accent-green">
            {savedAt ? '已保存 · 重启后生效' : ''}
          </span>
          <div className="flex gap-2">
            <button
              onClick={onDismiss}
              className="px-4 py-1.5 rounded text-sm text-text-muted border border-border-panel hover:border-accent-blue/40 hover:text-text-primary transition-colors"
            >
              关闭
            </button>
            <button
              onClick={handleSave}
              disabled={saving || loading}
              className="px-4 py-1.5 rounded text-sm text-white font-medium bg-accent-blue/80 hover:bg-accent-blue disabled:opacity-40 transition-colors"
            >
              {saving ? '保存中…' : '保存'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
