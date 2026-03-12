"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { apiFetch, setCurrentOrgId } from "@/lib/apiClient";

export type SessionUser = {
  id: string;
  email: string;
  is_system_admin: boolean;
  current_organization?: {
    id: string;
    slug: string;
    name?: string;
    role: string;
  };
  available_organizations: Array<{ id: string; slug: string; name?: string; role: string }>;
};

type AuthContextType = {
  user: SessionUser | null;
  loading: boolean;
  setOrg: (orgId: string) => void;
  isManager: boolean;
};

const AuthContext = createContext<AuthContextType>({ user: null, loading: true, setOrg: () => {}, isManager: false });

export function useAuth() {
  return useContext(AuthContext);
}

export default function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [loading, setLoading] = useState(true);
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    // Do not bootstrap session on public pages like login
    if (pathname === "/login") {
      setTimeout(() => setLoading(false), 0);
      return;
    }

    // Call /me to validate token or trigger silent refresh
    apiFetch("/api/auth/me")
      .then(async (res) => {
        if (res.ok) {
          const data = await res.json();
          // The backend returns { user: {...}, current_org: {...}, orgs: [...] }
          setUser({
            id: data.user.id,
            email: data.user.email,
            is_system_admin: !!data.user.is_system_admin,
            current_organization: data.current_org && data.current_org.id ? {
              id: data.current_org.id,
              slug: data.current_org.slug,
              name: data.current_org.name || "",
              role: data.current_org.role || data.membership?.role || ""
            } : undefined,
            available_organizations: (data.orgs || []).map((o: Record<string, string>) => ({
              id: o.id,
              slug: o.slug,
              name: o.name || "",
              role: o.role || ""
            }))
          });
          
          // Try to sync with apiClient
          if (data.current_org && data.current_org.id) {
              setCurrentOrgId(data.current_org.id);
          }
          setLoading(false);
        } else {
          router.push("/login");
        }
      })
      .catch(() => {
        router.push("/login");
      });
  }, [pathname, router]);

  const setOrg = (orgId: string) => {
      setCurrentOrgId(orgId);
      // Reload page to re-fetch all data with new header
      if (typeof window !== 'undefined') {
          window.location.reload();
      }
  };

  // Compute isManager: user is manager if system admin, or has GERENTE/OWNER/ADMIN role in current org
  const currentRole = user?.current_organization?.role || "";
  const isManager = !!user?.is_system_admin || ["GERENTE", "OWNER", "ADMIN"].includes(currentRole);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-50 text-gray-500">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mr-3"></div>
        <span>Carregando sessão...</span>
      </div>
    );
  }

  return (
    <AuthContext.Provider value={{ user, loading, setOrg, isManager }}>
        {children}
    </AuthContext.Provider>
  );
}
