'use client';

import React, { useState } from 'react';
import { Bot, Send, AlertTriangle, ShieldCheck, PhoneCall, Sparkles, User, RefreshCw } from 'lucide-react';
import { TruthStatusBadge } from '@/components/layout/TruthStatusBadge';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  isEmergency?: boolean;
  emergencyNumbers?: string[];
  suggestedActions?: Array<{ title: string; action_type: string }>;
  timestamp: string;
}

const INITIAL_MESSAGES: ChatMessage[] = [
  {
    id: 'm-init',
    role: 'assistant',
    content: "Hello Rahul. I am the ZENDOC AI Health Advisor. You can ask me questions about symptoms, preventive wellness, nutrition, or lab test interpretations.\n\n**Important:** I provide educational guidance, not an autonomous medical diagnosis. In case of acute chest pain, difficulty breathing, or stroke symptoms, please call emergency services immediately.",
    timestamp: 'Just now',
  },
];

export default function AIChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_MESSAGES);
  const [inputQuery, setInputQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [emergencyAlert, setEmergencyAlert] = useState<{ active: boolean; numbers: string[]; reason: string } | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputQuery.trim() || isLoading) return;

    const userText = inputQuery.trim();
    setInputQuery('');

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: userText,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const res = await fetch('/api/ai/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userText }),
      });

      const data = await res.json();

      if (data.is_emergency) {
        setEmergencyAlert({
          active: true,
          numbers: data.triage.emergency_numbers,
          reason: data.triage.reason,
        });
      }

      const assistantMsg: ChatMessage = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        content: data.content,
        isEmergency: data.is_emergency,
        emergencyNumbers: data.triage?.emergency_numbers,
        suggestedActions: data.suggested_actions,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch {
      const errorMsg: ChatMessage = {
        id: `err-${Date.now()}`,
        role: 'assistant',
        content: 'Unable to reach the advisory service. Please check your network connection or consult your healthcare provider directly.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  const triggerSampleEmergency = () => {
    setInputQuery("I have crushing chest pain radiating to my left arm and I can't breathe.");
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      {/* Top Banner */}
      <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Bot className="w-6 h-6 text-indigo-600" />
            <h1 className="text-xl font-bold text-slate-900">ZENDOC AI Advisory Assistant</h1>
            <TruthStatusBadge status="WORKING" />
          </div>
          <p className="text-xs text-slate-500">
            Deterministic emergency-first gate â€¢ Minimum-necessary context â€¢ No autonomous prescribing
          </p>
        </div>

        {/* Safety test trigger */}
        <button
          type="button"
          onClick={triggerSampleEmergency}
          className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 hover:bg-amber-100 transition"
        >
          Test Red-Flag Emergency Triage
        </button>
      </div>

      {/* Emergency Modal Alert if triggered */}
      {emergencyAlert && (
        <div className="p-4 rounded-xl bg-red-50 border-2 border-red-500 text-red-950 space-y-2 animate-bounce-short">
          <div className="flex items-center gap-2 font-bold text-sm text-red-800">
            <AlertTriangle className="w-5 h-5 text-red-600" />
            <span>CRITICAL MEDICAL EMERGENCY DETECTED</span>
          </div>
          <p className="text-xs leading-relaxed font-medium">
            {emergencyAlert.reason} AI inference has been aborted. Please call your local emergency service immediately:
          </p>
          <div className="flex flex-wrap gap-2 pt-1">
            {emergencyAlert.numbers.map((num) => (
              <a
                key={num}
                href={`tel:${num.split(' ')[0]}`}
                className="px-3 py-1 rounded bg-red-600 text-white font-bold text-xs hover:bg-red-700 transition flex items-center gap-1.5"
              >
                <PhoneCall className="w-3.5 h-3.5" />
                <span>Call {num}</span>
              </a>
            ))}
          </div>
        </div>
      )}

      {/* Chat Messages Log */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col h-[540px]">
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
          {messages.map((m) => (
            <div
              key={m.id}
              className={`flex gap-3 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {m.role === 'assistant' && (
                <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${m.isEmergency ? 'bg-red-600 text-white' : 'bg-indigo-600 text-white'}`}>
                  {m.isEmergency ? <AlertTriangle className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
                </div>
              )}

              <div
                className={`max-w-[85%] rounded-2xl p-4 text-xs sm:text-sm leading-relaxed ${
                  m.role === 'user'
                    ? 'bg-sky-600 text-white'
                    : m.isEmergency
                    ? 'bg-red-50 border border-red-200 text-red-950 font-medium'
                    : 'bg-slate-100 text-slate-800'
                }`}
              >
                <div className="whitespace-pre-wrap">{m.content}</div>

                {m.suggestedActions && m.suggestedActions.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-slate-200/50 space-y-1.5">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 block">Suggested Actions:</span>
                    <div className="flex flex-wrap gap-2">
                      {m.suggestedActions.map((act) => (
                        <button
                          key={act.title}
                          type="button"
                          className="px-2.5 py-1 rounded-lg bg-white border border-slate-200 text-slate-700 font-semibold text-xs hover:bg-slate-50 transition"
                        >
                          {act.title}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <div className={`mt-2 text-[10px] ${m.role === 'user' ? 'text-sky-200' : 'text-slate-400'} text-right`}>
                  {m.timestamp}
                </div>
              </div>

              {m.role === 'user' && (
                <div className="w-8 h-8 rounded-full bg-slate-200 text-slate-700 flex items-center justify-center shrink-0">
                  <User className="w-4 h-4" />
                </div>
              )}
            </div>
          ))}

          {isLoading && (
            <div className="flex gap-3 items-center text-slate-500 text-xs">
              <div className="w-8 h-8 rounded-full bg-indigo-100 text-indigo-600 flex items-center justify-center">
                <RefreshCw className="w-4 h-4 animate-spin" />
              </div>
              <span>Evaluating query through clinical safety triage...</span>
            </div>
          )}
        </div>

        {/* Chat Input Bar */}
        <form onSubmit={handleSubmit} className="p-3 border-t border-slate-200 flex items-center gap-2 bg-slate-50 rounded-b-2xl">
          <input
            type="text"
            placeholder="Describe your health question or symptom..."
            value={inputQuery}
            onChange={(e) => setInputQuery(e.target.value)}
            disabled={isLoading}
            className="flex-1 bg-white px-4 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          <button
            type="submit"
            disabled={isLoading || !inputQuery.trim()}
            className="px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-semibold text-sm transition flex items-center gap-1.5 shadow-sm"
          >
            <span>Send</span>
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </div>
  );
}
