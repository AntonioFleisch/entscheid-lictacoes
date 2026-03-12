"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import Image from "next/image";
import Link from "next/link";
import LogoutButton from "@/components/LogoutButton";
import { useAuth } from "./AuthProvider";

export default function SiteHeader() {
  const pathname = usePathname();
  const { user, setOrg, loading, isManager } = useAuth();
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setIsMounted(true), 10);
    return () => clearTimeout(timer);
  }, []);

  if (pathname === "/login") {
    return null;
  }

  return (
    <header className="bg-white border-b border-gray-200 min-h-[57px]">
      <div className="flex items-center justify-between px-6 py-3">
        <div className="flex items-center gap-8">
          <Link href="/" className="flex items-center">
            <Image 
              src="/entscheid.png" 
              alt="Entscheid" 
              width={150} 
              height={32} 
              className="h-8 w-auto object-contain"
              priority
            />
          </Link>

          {isMounted && user && user.available_organizations && user.available_organizations.length > 0 && (
            <div className="flex items-center gap-2 text-sm text-gray-700 font-medium animate-in fade-in">
              <span className="text-gray-400">|</span>
              <select 
                className="bg-transparent border-none outline-none cursor-pointer hover:text-blue-600 focus:ring-0"
                value={user.current_organization?.id || ""}
                onChange={(e) => setOrg(e.target.value)}
              >
                {user.available_organizations.map(org => (
                  <option key={org.id} value={org.id}>{org.name || org.slug}</option>
                ))}
              </select>
            </div>
          )}
        </div>

        <nav className="flex items-center gap-3">
          {isMounted && !loading && isManager && (
            <Link 
              href="/org/members" 
              className="text-sm font-medium border border-green-300 text-green-700 hover:bg-green-50 px-3 py-1.5 rounded-md transition-colors animate-in fade-in"
            >
              Gerenciar Org
            </Link>
          )}
          {isMounted && !loading && user?.is_system_admin && (
            <Link 
              href="/admin/organizations" 
              className="text-sm font-medium border border-[#98c1d9] text-[#3d5a80] hover:bg-[#e0fbfc] px-3 py-1.5 rounded-md transition-colors animate-in fade-in"
            >
              Painel ADM
            </Link>
          )}
          {isMounted && <LogoutButton />}
        </nav>
      </div>
    </header>
  );
}
