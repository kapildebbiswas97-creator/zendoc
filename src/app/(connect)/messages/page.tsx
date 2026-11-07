'use client';

import React, { useState } from 'react';
import { MessageSquare, Send, Video, Phone, ShieldCheck, User, Paperclip } from 'lucide-react';
import { TruthStatusBadge } from '@/components/layout/TruthStatusBadge';

interface Message {
  id: string;
  sender: 'me' | 'other';
  senderName: string;
  text: string;
  time: string;
}

const INITIAL_MESSAGES: Message[] = [
  {
    id: 'm1',
    sender: 'other',
    senderName: 'Dr. Debabrata Sen',
    text: 'Good afternoon Rahul. I reviewed your recent lipid profile. Total cholesterol and triglycerides look very well controlled.',
    time: '02:15 PM',
  },
  {
    id: 'm2',
    sender: 'me',
    senderName: 'Rahul Sharma',
    text: 'Thank you doctor! Should I continue the same dosage of Telmisartan 40mg?',
    time: '02:18 PM',
  },
  {
    id: 'm3',
    sender: 'other',
    senderName: 'Dr. Debabrata Sen',
    text: 'Yes, continue the exact same dose. Keep logging your morning blood pressure twice a week.',
    time: '02:20 PM',
  },
];

export default function ConnectMessagesPage() {
  const [messages, setMessages] = useState<Message[]>(INITIAL_MESSAGES);
  const [inputText, setInputText] = useState('');
  const [inCall, setInCall] = useState(false);

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim()) return;

    const newMsg: Message = {
      id: `m-${Date.now()}`,
      sender: 'me',
      senderName: 'Rahul Sharma',
      text: inputText.trim(),
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages([...messages, newMsg]);
    setInputText('');
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold text-slate-900">ZENDOC Connect â€” Clinical Messaging & Consultations</h1>
            <TruthStatusBadge status="WORKING" />
          </div>
          <p className="text-xs text-slate-500 mt-1">
            End-to-end authenticated clinical messaging and encrypted WebRTC video consultation rooms.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setInCall(!inCall)}
            className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-sm transition flex items-center gap-1.5"
          >
            <Video className="w-3.5 h-3.5" />
            <span>{inCall ? 'End Telehealth Call' : 'Start Telehealth Call'}</span>
          </button>
        </div>
      </div>

      {/* Active Telehealth Simulation Banner */}
      {inCall && (
        <div className="p-6 rounded-2xl bg-slate-900 text-white space-y-4 shadow-xl border border-slate-700">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
              <span className="font-bold text-sm">Encrypted Video Consultation (Dr. Debabrata Sen)</span>
            </div>
            <span className="text-xs text-slate-400 font-mono">WebRTC P2P Signaling Active</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 h-64">
            <div className="bg-slate-800 rounded-xl flex items-center justify-center border border-slate-700 relative overflow-hidden">
              <div className="text-center space-y-2">
                <div className="w-16 h-16 rounded-full bg-slate-700 flex items-center justify-center mx-auto text-xl font-bold text-sky-400">
                  DS
                </div>
                <p className="text-xs font-semibold text-slate-200">Dr. Debabrata Sen (Cardiologist)</p>
                <span className="text-[10px] text-emerald-400">Camera & Audio Connected</span>
              </div>
            </div>

            <div className="bg-slate-800 rounded-xl flex items-center justify-center border border-slate-700 relative overflow-hidden">
              <div className="text-center space-y-2">
                <div className="w-16 h-16 rounded-full bg-slate-700 flex items-center justify-center mx-auto text-xl font-bold text-slate-400">
                  You
                </div>
                <p className="text-xs font-semibold text-slate-200">Rahul Sharma (Patient)</p>
                <span className="text-[10px] text-emerald-400">Self View (Encrypted)</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Main Messaging Interface */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col h-[520px]">
        {/* Chat partner header */}
        <div className="p-4 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-sky-100 text-sky-800 flex items-center justify-center font-bold text-sm">
              DS
            </div>
            <div>
              <h2 className="font-bold text-sm text-slate-900">Dr. Debabrata Sen</h2>
              <p className="text-xs text-emerald-600 font-medium">Online â€¢ Verified Cardiologist</p>
            </div>
          </div>
          <span className="text-xs text-slate-400">Consultation Channel <code>c-9914</code></span>
        </div>

        {/* Message feed */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex flex-col ${msg.sender === 'me' ? 'items-end' : 'items-start'}`}
            >
              <div
                className={`max-w-[75%] rounded-2xl p-3.5 text-xs leading-relaxed ${
                  msg.sender === 'me'
                    ? 'bg-sky-600 text-white rounded-br-xs'
                    : 'bg-slate-100 text-slate-800 rounded-bl-xs'
                }`}
              >
                <p>{msg.text}</p>
                <span
                  className={`text-[9px] block mt-1.5 ${
                    msg.sender === 'me' ? 'text-sky-200' : 'text-slate-400'
                  } text-right`}
                >
                  {msg.time}
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* Chat input */}
        <form onSubmit={handleSend} className="p-3 border-t border-slate-100 bg-slate-50 rounded-b-2xl flex items-center gap-2">
          <input
            type="text"
            placeholder="Type your message to Dr. Sen..."
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            className="flex-1 bg-white px-4 py-2.5 rounded-xl border border-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-sky-500"
          />
          <button
            type="submit"
            className="px-4 py-2.5 rounded-xl bg-sky-600 hover:bg-sky-700 text-white font-semibold text-xs shadow-sm transition flex items-center gap-1.5"
          >
            <span>Send</span>
            <Send className="w-3.5 h-3.5" />
          </button>
        </form>
      </div>
    </div>
  );
}
