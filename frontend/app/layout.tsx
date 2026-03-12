import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import AuthProvider from "@/components/AuthProvider";
import SiteHeader from "@/components/SiteHeader";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Entscheid",
  description: "Monitoramento de Licitações Públicas",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR">
      <body className={inter.className}>
        <div className="flex flex-col h-screen bg-gray-50">
          <AuthProvider>
            <SiteHeader />
            <main className="flex-1 overflow-hidden">
                 {children}
            </main>
          </AuthProvider>
        </div>
      </body>
    </html>
  );
}
