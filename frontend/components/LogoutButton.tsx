"use client";

import { useRouter } from "next/navigation";
import { apiFetch, setAccessToken } from "@/lib/apiClient";

export default function LogoutButton() {
  const router = useRouter();

  const handleLogout = async () => {
    try {
      await apiFetch("/api/auth/logout", { method: "POST" });
    } catch (e) {
      console.error(e);
    } finally {
      setAccessToken(null);
      router.push("/login");
    }
  };

  return (
    <button 
      onClick={handleLogout} 
      className="text-sm font-medium text-gray-600 hover:text-gray-900 border border-gray-300 rounded px-3 py-1"
    >
      Sair
    </button>
  );
}
