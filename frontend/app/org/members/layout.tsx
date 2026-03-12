"use client";

import { useAuth } from "@/components/AuthProvider";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function OrgMembersLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  const isManager = user?.is_system_admin ||
    user?.current_organization?.role === "GERENTE" ||
    user?.current_organization?.role === "OWNER" ||
    user?.current_organization?.role === "ADMIN";

  useEffect(() => {
    if (!loading && user && !isManager) {
      router.replace("/licitacoes");
    }
  }, [user, loading, router, isManager]);

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (!user || !isManager) {
    return null;
  }

  return (
    <div className="flex flex-col min-h-screen bg-gray-50">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 w-full py-8">
        {children}
      </div>
    </div>
  );
}
