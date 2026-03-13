import * as React from 'react'
import { cn } from '@/lib/utils'

export interface SelectProps
  extends React.SelectHTMLAttributes<HTMLSelectElement> {}

const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, children, ...props }, ref) => {
    return (
      <select
        className={cn(
          "flex h-10 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm ring-offset-white file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-slate-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-800 dark:bg-slate-950 dark:ring-offset-slate-950 dark:placeholder:text-slate-400 dark:focus-visible:ring-blue-500",
          className
        )}
        ref={ref}
        {...props}
      >
        {children}
      </select>
    )
  }
)
Select.displayName = 'Select'

export interface SelectTriggerProps {
  children: React.ReactNode
  className?: string
}

export const SelectTrigger = ({ children, className }: SelectTriggerProps) => {
  return (
    <div className={cn("relative", className)}>
      {children}
    </div>
  )
}

export interface SelectValueProps {
  placeholder?: string
}

export const SelectValue = ({ placeholder }: SelectValueProps) => {
  return <span className="text-slate-500">{placeholder}</span>
}

export interface SelectContentProps {
  children: React.ReactNode
  className?: string
}

export const SelectContent = ({ children, className }: SelectContentProps) => {
  return (
    <div className={cn(
      "absolute top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg z-50 max-h-60 overflow-auto dark:bg-slate-900 dark:border-slate-700",
      className
    )}>
      {children}
    </div>
  )
}

export interface SelectItemProps {
  children: React.ReactNode
  value: string
  className?: string
}

export const SelectItem = ({ children, value, className }: SelectItemProps) => {
  return (
    <button
      type="button"
      value={value}
      className={cn(
        "w-full text-left px-3 py-2 hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer",
        className
      )}
    >
      {children}
    </button>
  )
}

export { Select }