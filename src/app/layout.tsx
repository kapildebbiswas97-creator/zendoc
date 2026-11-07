import type { Metadata } from 'next';
import './globals.css';
import { Navbar } from '@/components/layout/Navbar';
import { Footer } from '@/components/layout/Footer';
import { EmergencyBanner } from '@/components/layout/EmergencyBanner';

export const metadata: Metadata = {
  title: 'ZENDOC 2.0 â€” AI-Powered Healthcare Coordination Platform',
  description: 'Next-generation patient health memory, verified provider discovery, and safety-governed AI advisory platform.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full">
      <body className="flex flex-col min-h-screen bg-slate-50 text-slate-900 antialiased">
        <EmergencyBanner />
        <Navbar />
        <main className="flex-1 w-full">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
