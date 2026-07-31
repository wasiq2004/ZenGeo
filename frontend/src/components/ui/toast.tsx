import * as ToastPrimitive from '@radix-ui/react-toast'
import { CheckCircle2, TriangleAlert, X, XCircle } from 'lucide-react'
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

type ToastVariant = 'default' | 'success' | 'error' | 'warning'

interface ToastItem {
  id: number
  title: string
  description?: string
  variant: ToastVariant
}

interface ToastContextValue {
  toast: (input: { title: string; description?: string; variant?: ToastVariant }) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

let nextId = 0

const variantStyles: Record<ToastVariant, { border: string; Icon: typeof CheckCircle2 | null; iconClass: string }> = {
  default: { border: 'border-border', Icon: null, iconClass: '' },
  success: { border: 'border-success/40', Icon: CheckCircle2, iconClass: 'text-success' },
  error: { border: 'border-destructive/40', Icon: XCircle, iconClass: 'text-destructive' },
  warning: { border: 'border-warning/40', Icon: TriangleAlert, iconClass: 'text-warning' },
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])

  const toast = useCallback<ToastContextValue['toast']>(({ title, description, variant = 'default' }) => {
    setItems((current) => [...current, { id: nextId++, title, description, variant }])
  }, [])

  const dismiss = useCallback((id: number) => {
    setItems((current) => current.filter((item) => item.id !== id))
  }, [])

  const value = useMemo(() => ({ toast }), [toast])

  return (
    <ToastContext.Provider value={value}>
      <ToastPrimitive.Provider swipeDirection="right" duration={6000}>
        {children}
        {items.map((item) => {
          const style = variantStyles[item.variant]
          return (
            <ToastPrimitive.Root
              key={item.id}
              onOpenChange={(open) => !open && dismiss(item.id)}
              className={cn(
                'pointer-events-auto flex w-full items-start gap-3 rounded-lg border bg-popover p-4 text-popover-foreground shadow-lg',
                'data-[state=open]:animate-fade-in data-[swipe=end]:translate-x-[var(--radix-toast-swipe-end-x)]',
                style.border,
              )}
            >
              {style.Icon && (
                <style.Icon className={cn('mt-0.5 size-4 shrink-0', style.iconClass)} aria-hidden="true" />
              )}
              <div className="min-w-0 flex-1 space-y-0.5">
                <ToastPrimitive.Title className="text-sm font-medium leading-snug">
                  {item.title}
                </ToastPrimitive.Title>
                {item.description && (
                  <ToastPrimitive.Description className="text-sm text-muted-foreground">
                    {item.description}
                  </ToastPrimitive.Description>
                )}
              </div>
              <ToastPrimitive.Close
                aria-label="Dismiss notification"
                className="rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground"
              >
                <X className="size-4" aria-hidden="true" />
              </ToastPrimitive.Close>
            </ToastPrimitive.Root>
          )
        })}
        <ToastPrimitive.Viewport className="pointer-events-none fixed bottom-0 right-0 z-[100] flex max-h-screen w-full flex-col gap-2 p-4 sm:max-w-sm" />
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useToast() {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast must be used inside <ToastProvider>')
  return context
}
