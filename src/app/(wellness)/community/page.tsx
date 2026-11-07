'use client';

import React, { useState } from 'react';
import { Users, Heart, MessageSquare, Plus, ShieldCheck, Sparkles } from 'lucide-react';
import { TruthStatusBadge } from '@/components/layout/TruthStatusBadge';

const SAMPLE_POSTS = [
  {
    id: 'p1',
    author: 'Ananya G.',
    category: 'Cardiac Wellness',
    title: 'My 6-month journey reversing borderline hypertension through brisk morning walks',
    content: 'When my BP measured 142/90 in March, my doctor recommended 45 minutes of daily brisk walking and reducing sodium intake. Today my morning reading was 118/78! Consistency in daily logging really helped me stay accountable.',
    likes: 42,
    comments: 8,
    time: '2 hours ago',
  },
  {
    id: 'p2',
    author: 'Siddharth M.',
    category: 'Diabetes Management',
    title: 'Healthy Bengali breakfast ideas that donâ€™t cause sharp glucose spikes',
    content: 'Sharing a quick tip: Replacing white puffed rice (muri) with roasted chana and boiled eggs stabilized my 2-hour post-prandial blood sugar below 135 mg/dL. Would love to hear other low-glycemic options you all enjoy!',
    likes: 29,
    comments: 14,
    time: 'Yesterday',
  },
];

export default function CommunityPage() {
  const [posts, setPosts] = useState(SAMPLE_POSTS);

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-8">
      {/* Header */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">Health Community & Peer Support</h1>
            <TruthStatusBadge status="WORKING" />
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Safe, moderated peer discussions and patient recovery stories.
          </p>
        </div>

        <button
          type="button"
          className="px-4 py-2 rounded-xl bg-sky-600 hover:bg-sky-700 text-white text-sm font-semibold shadow-sm transition flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          <span>Share Story</span>
        </button>
      </div>

      {/* Moderation Disclaimer */}
      <div className="p-4 rounded-xl bg-slate-100 border border-slate-300 text-slate-700 text-xs">
        <strong>Community Invariant:</strong> Patient peer stories and tips reflect individual experiences and do not constitute verified clinical advice or treatment protocols.
      </div>

      {/* Posts Stream */}
      <div className="space-y-6">
        {posts.map((post) => (
          <article
            key={post.id}
            className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-3"
          >
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-full bg-sky-100 text-sky-800 flex items-center justify-center font-bold">
                  {post.author[0]}
                </div>
                <span className="font-semibold text-slate-800">{post.author}</span>
                <span className="text-slate-400">â€¢</span>
                <span className="text-slate-400">{post.time}</span>
              </div>
              <span className="px-2.5 py-0.5 rounded-full bg-sky-50 text-sky-700 font-semibold text-[10px]">
                {post.category}
              </span>
            </div>

            <h2 className="text-base font-bold text-slate-900">{post.title}</h2>
            <p className="text-xs text-slate-600 leading-relaxed">{post.content}</p>

            <div className="flex items-center gap-4 pt-3 border-t border-slate-100 text-xs text-slate-500 font-semibold">
              <button
                type="button"
                className="flex items-center gap-1.5 hover:text-rose-600 transition"
              >
                <Heart className="w-4 h-4 text-rose-500" />
                <span>{post.likes} Helpful</span>
              </button>

              <button
                type="button"
                className="flex items-center gap-1.5 hover:text-sky-600 transition"
              >
                <MessageSquare className="w-4 h-4 text-sky-500" />
                <span>{post.comments} Responses</span>
              </button>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
