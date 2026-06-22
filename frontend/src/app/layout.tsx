import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Navbar } from "@/components/layout/navbar";
import { AppProvider } from "@/context/app-context";
import { ToastProvider } from "@/context/toast-context";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "RecruitIQ AI — AI-Augmented Recruitment Platform",
  description: "Screen 1,000 CVs. Surface the 10 who matter. Explain why.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} antialiased`}>
        <ToastProvider>
          <AppProvider>
            <Navbar />
            <main>{children}</main>
          </AppProvider>
        </ToastProvider>
      </body>
    </html>
  );
}
