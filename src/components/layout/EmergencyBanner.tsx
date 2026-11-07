import React from 'react';
import { AlertTriangle, PhoneCall } from 'lucide-react';

export function EmergencyBanner() {
  return (
    <aside
      aria-label="Medical emergency notification"
      className="bg-amber-500 text-amber-950 px-4 py-2 text-xs md:text-sm font-medium border-b border-amber-600 shadow-sm"
    >
      <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-950 shrink-0" aria-hidden="true" />
          <span>
            <strong>Medical Emergency?</strong> Call <a href="tel:102" className="underline font-bold hover:text-black">102</a> / <a href="tel:108" className="underline font-bold hover:text-black">108</a> (India) or <a href="tel:112" className="underline font-bold hover:text-black">112</a> immediately.
          </span>
        </div>
        <div className="flex items-center gap-2">
          <PhoneCall className="w-3.5 h-3.5" aria-hidden="true" />
          <span className="text-amber-950/80">AI is educational only â€” never replaces an ER.</span>
        </div>
      </div>
    </aside>
  );
}
