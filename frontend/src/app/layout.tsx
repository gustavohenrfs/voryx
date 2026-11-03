import type { Metadata, Viewport } from "next";
import { Fraunces, Manrope } from "next/font/google";
import { ToastProvider } from "@/components/ui/Toast";
import "./globals.css";

const fraunces = Fraunces({ subsets: ["latin"], variable: "--font-fraunces", axes: ["opsz"] });
const manrope = Manrope({ subsets: ["latin"], variable: "--font-manrope" });

export const metadata: Metadata = {
  title: "Voryx",
  description: "Painel dos grupos de prévias",
};

export const viewport: Viewport = { themeColor: "#0f0e0c", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" className={`${fraunces.variable} ${manrope.variable}`}>
      <body className="min-h-dvh">
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
