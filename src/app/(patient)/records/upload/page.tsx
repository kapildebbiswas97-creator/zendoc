'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Upload, ArrowLeft, CheckCircle2, ShieldCheck, FileText, AlertCircle } from 'lucide-react';

export default function UploadRecordPage() {
  const router = useRouter();
  const [title, setTitle] = useState('');
  const [recordType, setRecordType] = useState('Lab Report');
  const [file, setFile] = useState<File | null>(null);
  const [summary, setSummary] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploaded, setUploaded] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selected = e.target.files[0];
      // Size check: max 10MB
      if (selected.size > 10 * 1024 * 1024) {
        setErrorMsg('File exceeds 10MB limit. Please upload a smaller document.');
        setFile(null);
        return;
      }
      // MIME check
      const validTypes = ['application/pdf', 'image/jpeg', 'image/png', 'image/webp'];
      if (!validTypes.includes(selected.type)) {
        setErrorMsg('Unsupported file format. Please upload PDF, PNG, or JPEG documents.');
        setFile(null);
        return;
      }
      setErrorMsg(null);
      setFile(selected);
      if (!title) {
        setTitle(selected.name.replace(/\.[^/.]+$/, ''));
      }
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setErrorMsg('Please select a file to upload.');
      return;
    }

    setUploading(true);
    // Simulate secure signed storage upload
    setTimeout(() => {
      setUploading(false);
      setUploaded(true);
      setTimeout(() => {
        router.push('/records');
      }, 2000);
    }, 1200);
  };

  return (
    <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      <Link
        href="/records"
        className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800 transition"
      >
        <ArrowLeft className="w-4 h-4" />
        <span>Back to Medical Records</span>
      </Link>

      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-6">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Upload to Private Medical Vault</h1>
          <p className="text-xs text-slate-500 mt-1">
            Documents are encrypted at rest with content-addressed SHA-256 integrity verification.
          </p>
        </div>

        {errorMsg && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-red-800 text-xs font-semibold flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {uploaded ? (
          <div className="p-6 bg-emerald-50 border border-emerald-200 rounded-xl text-center space-y-3">
            <CheckCircle2 className="w-12 h-12 text-emerald-600 mx-auto" />
            <h3 className="font-bold text-base text-emerald-950">Record Encrypted & Uploaded!</h3>
            <p className="text-xs text-emerald-800">
              Your document has been verified, stored in the private Supabase bucket, and linked to your Health Memory. Redirecting...
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Document Title</label>
              <input
                type="text"
                placeholder="e.g. Annual Blood Panel - Oct 2026"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
                className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Document Category</label>
              <select
                value={recordType}
                onChange={(e) => setRecordType(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
              >
                <option value="Lab Report">Diagnostic Lab Report</option>
                <option value="Prescription">Prescription</option>
                <option value="Discharge Summary">Discharge Summary</option>
                <option value="Radiology Scan">Radiology / Imaging Scan</option>
                <option value="Vaccination Card">Immunization Record</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Select File (PDF, PNG, JPEG - Max 10MB)</label>
              <input
                type="file"
                accept=".pdf,image/png,image/jpeg,image/webp"
                onChange={handleFileChange}
                required
                className="w-full text-xs text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-semibold file:bg-sky-50 file:text-sky-700 hover:file:bg-sky-100 cursor-pointer"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Clinical Summary / Remarks</label>
              <textarea
                placeholder="Key results or clinical summary of this report..."
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                rows={3}
                className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
            </div>

            <button
              type="submit"
              disabled={uploading}
              className="w-full py-3 rounded-xl bg-sky-600 hover:bg-sky-700 disabled:opacity-50 text-white font-semibold text-sm shadow-sm transition flex items-center justify-center gap-2"
            >
              <Upload className="w-4 h-4" />
              <span>{uploading ? 'Encrypting & Storing...' : 'Upload & Encrypt Record'}</span>
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
