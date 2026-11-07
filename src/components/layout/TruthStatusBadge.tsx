import React from 'react';
import { TruthStatus } from '@/lib/types/healthcare';
import { cn } from '@/lib/utils/cn';

interface TruthStatusBadgeProps {
  status: TruthStatus;
  className?: string;
  showIcon?: boolean;
}

export function TruthStatusBadge({ status, className, showIcon = true }: TruthStatusBadgeProps) {
  const config = {
    WORKING: {
      label: 'VERIFIED WORKING',
      bg: 'bg-emerald-50 text-emerald-700 border-emerald-200',
      dot: 'bg-emerald-500',
    },
    BETA: {
      label: 'BETA PREVIEW',
      bg: 'bg-blue-50 text-blue-700 border-blue-200',
      dot: 'bg-blue-500',
    },
    INTEGRATION_REQUIRED: {
      label: 'INTEGRATION REQUIRED',
      bg: 'bg-amber-50 text-amber-700 border-amber-200',
      dot: 'bg-amber-500',
    },
    DISABLED: {
      label: 'POLICY DISABLED',
      bg: 'bg-slate-50 text-slate-600 border-slate-200',
      dot: 'bg-slate-400',
    },
    FUTURE: {
      label: 'PLANNED FUTURE',
      bg: 'bg-purple-50 text-purple-700 border-purple-200',
      dot: 'bg-purple-400',
    },
  }[status];

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold border tracking-wide uppercase',
        config.bg,
        className
      )}
    >
      {showIcon && <span className={cn('w-1.5 h-1.5 rounded-full animate-pulse', config.dot)} />}
      {config.label}
    </span>
  );
}
