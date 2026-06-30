/// <reference types="vite/client" />

interface Window {
  pywebview?: {
    api: Record<string, (...args: unknown[]) => Promise<unknown>>
  }
  __onBackendEvent?: (data: unknown) => void
}
