import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Activity, Plus } from "lucide-react";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Health Decision Arena",
  description: "Research, doctor and patient perspectives on a health condition. Information only, not medical advice.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col font-sans">
        <header className="no-print sticky top-0 z-30 border-b border-slate-200/80 bg-white/90 backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
            <Link href="/" className="flex items-center gap-2.5">
              <span className="flex size-8 items-center justify-center rounded-lg bg-brand text-white">
                <Activity className="size-4" aria-hidden />
              </span>
              <span className="font-semibold tracking-tight text-slate-900">Health Decision Arena</span>
            </Link>
            <nav className="flex items-center gap-3">
              <span className="hidden text-xs text-slate-500 md:block">Health information only, not medical advice</span>
              <Link
                href="/"
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50"
              >
                <Plus className="size-4" aria-hidden />
                New session
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 sm:py-8">{children}</main>
        <footer className="no-print border-t border-slate-200 bg-white">
          <div className="mx-auto max-w-7xl px-4 py-4 text-xs leading-relaxed text-slate-500 sm:px-6">
            This tool summarises published research, clinical references and patient experiences found on the web. It is
            health information to discuss with a qualified clinician, not a diagnosis or a prescription. Never start,
            stop or change a medication based on it. If you have emergency warning signs, seek urgent care now.
          </div>
        </footer>
      </body>
    </html>
  );
}
