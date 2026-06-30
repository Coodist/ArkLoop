import { useEffect, useRef, useState } from 'react'

interface ResizeHandlesProps {
  getWindowBounds: () => Promise<{ x: number; y: number; width: number; height: number }>
  setBounds: (x: number, y: number, width: number, height: number) => Promise<void> | void
}

type ResizeDir = 'right' | 'bottom' | 'corner'

export function ResizeHandles({ getWindowBounds, setBounds }: ResizeHandlesProps) {
  const [dragging, setDragging] = useState<ResizeDir | null>(null)
  const startRef = useRef({
    mouseScreenX: 0,
    mouseScreenY: 0,
    x: 0,
    y: 0,
    width: 0,
    height: 0,
  })

  const onMouseDown = async (dir: ResizeDir, e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    const bounds = await getWindowBounds()
    startRef.current = {
      mouseScreenX: (window.screenX ?? 0) + e.clientX,
      mouseScreenY: (window.screenY ?? 0) + e.clientY,
      x: bounds.x,
      y: bounds.y,
      width: bounds.width,
      height: bounds.height,
    }
    setDragging(dir)
  }

  useEffect(() => {
    if (!dragging) return

    const onMove = async (e: MouseEvent) => {
      const start = startRef.current
      const screenX = (window.screenX ?? 0) + e.clientX
      const screenY = (window.screenY ?? 0) + e.clientY
      const dx = screenX - start.mouseScreenX
      const dy = screenY - start.mouseScreenY

      let width = start.width
      let height = start.height
      if (dragging === 'right' || dragging === 'corner') {
        width = Math.max(946, start.width + dx)
      }
      if (dragging === 'bottom' || dragging === 'corner') {
        height = Math.max(666, start.height + dy)
      }

      await setBounds(start.x, start.y, width, height)
    }

    const onUp = () => setDragging(null)

    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [dragging, setBounds])

  return (
    <div className="fixed inset-0 pointer-events-none z-[100]">
      <div
        className="absolute right-0 top-0 bottom-0 w-[6px] cursor-e-resize pointer-events-auto"
        onMouseDown={(e) => onMouseDown('right', e)}
      />
      <div
        className="absolute left-0 right-0 bottom-0 h-[6px] cursor-s-resize pointer-events-auto"
        onMouseDown={(e) => onMouseDown('bottom', e)}
      />
      <div
        className="absolute right-0 bottom-0 w-[12px] h-[12px] cursor-se-resize pointer-events-auto"
        onMouseDown={(e) => onMouseDown('corner', e)}
      />
    </div>
  )
}
