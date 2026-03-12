"use client";

import Link from "next/link";
import { Building2, Users } from "lucide-react";

export default function AdminDashboard() {
  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Admin Console</h1>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <Link href="/admin/organizations" className="block">
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 hover:shadow-md transition-shadow">
            <div className="flex items-center gap-4 mb-4">
              <div className="bg-blue-100 p-3 rounded-lg text-blue-600">
                <Building2 className="w-6 h-6" />
              </div>
              <h2 className="text-lg font-semibold text-gray-900">Organizations</h2>
            </div>
            <p className="text-gray-500 text-sm">
              Manage multi-tenant business units, view active subscriptions, and configure top-level features.
            </p>
          </div>
        </Link>
        
        <Link href="/admin/users" className="block">
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 hover:shadow-md transition-shadow">
            <div className="flex items-center gap-4 mb-4">
              <div className="bg-green-100 p-3 rounded-lg text-green-600">
                <Users className="w-6 h-6" />
              </div>
              <h2 className="text-lg font-semibold text-gray-900">Users</h2>
            </div>
            <p className="text-gray-500 text-sm">
              Manage system users, reset passwords, and audit login events across the platform.
            </p>
          </div>
        </Link>
      </div>
    </div>
  );
}
