"use client";

import { useState } from "react";
import { Plus, Search, Users, X, Loader2, Trash2, Shield, User as UserIcon } from "lucide-react";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";
import { useOrgMembers } from "@/lib/hooks";
import { addOrgMember, removeOrgMember } from "@/lib/api";

interface Member {
  id: string;
  user_id: string;
  email: string;
  name: string;
  role: string;
  created_at: string;
}

const ROLE_BADGES: Record<string, { label: string; color: string }> = {
  ADMIN: { label: "Admin", color: "bg-purple-100 text-purple-800" },
  OWNER: { label: "Dono", color: "bg-amber-100 text-amber-800" },
  GERENTE: { label: "Gerente", color: "bg-green-100 text-green-800" },
  USUARIO: { label: "Membro", color: "bg-blue-100 text-blue-800" },
};

function MemberRow({ member, orgId, onMutate, canManage, isAdmin }: {
  member: Member;
  orgId: string;
  onMutate: () => Promise<void>;
  canManage: boolean;
  isAdmin: boolean;
}) {
  const { user } = useAuth();
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState("");
  const isSelf = member.user_id === user?.id;

  const badge = ROLE_BADGES[member.role] || ROLE_BADGES.USUARIO;

  const handleRemove = async () => {
    try {
      setIsDeleting(true);
      await removeOrgMember(orgId, member.id);
      await onMutate();
      setIsConfirmingDelete(false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erro ao remover");
      setIsDeleting(false);
    }
  };

  // Can only remove if: canManage AND not self AND (isAdmin OR member is USUARIO)
  const canRemove = canManage && !isSelf && (isAdmin || member.role === "USUARIO");

  return (
    <>
      <tr className="hover:bg-gray-50 transition-colors group">
        <td className="px-6 py-4">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-full ${member.role === "GERENTE" ? "bg-green-50 text-green-600" : "bg-blue-50 text-blue-600"}`}>
              {member.role === "GERENTE" || member.role === "OWNER" || member.role === "ADMIN"
                ? <Shield className="w-4 h-4" />
                : <UserIcon className="w-4 h-4" />
              }
            </div>
            <div>
              <span className="font-medium text-gray-900">{member.name}</span>
              {isSelf && <span className="ml-2 text-xs text-gray-400">(você)</span>}
            </div>
          </div>
        </td>
        <td className="px-6 py-4 text-gray-500 text-sm">{member.email}</td>
        <td className="px-6 py-4">
          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${badge.color}`}>
            {badge.label}
          </span>
        </td>
        <td className="px-6 py-4 text-gray-500 text-sm">{new Date(member.created_at).toLocaleDateString()}</td>
        <td className="px-6 py-4 text-right">
          {canRemove && (
            <div className="flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                onClick={() => setIsConfirmingDelete(true)}
                className="text-gray-400 hover:text-red-600 transition-colors p-1.5 rounded-md hover:bg-red-50 text-sm font-medium"
              >
                Remover
              </button>
            </div>
          )}
        </td>
      </tr>

      {/* Delete Confirmation Modal */}
      {isConfirmingDelete && (
        <tr>
          <td colSpan={5} className="p-0">
            <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
              <div className="bg-white rounded-xl shadow-xl w-full max-w-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-gray-100">
                  <h3 className="text-lg font-semibold text-gray-900">Confirmar remoção</h3>
                </div>
                <div className="p-6">
                  {error && <div className="mb-4 p-3 bg-red-50 text-red-700 text-sm rounded-lg">{error}</div>}
                  <p className="text-sm text-gray-600">
                    Tem certeza que deseja remover <strong>{member.name}</strong> ({member.email}) desta organização?
                  </p>
                  <div className="mt-6 flex justify-end gap-3">
                    <button onClick={() => { setIsConfirmingDelete(false); setError(""); }} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border rounded-lg hover:bg-gray-50" disabled={isDeleting}>Cancelar</button>
                    <button onClick={handleRemove} disabled={isDeleting} className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 flex items-center min-w-[100px] justify-center">
                      {isDeleting ? <Loader2 className="w-5 h-5 animate-spin" /> : <><Trash2 className="w-4 h-4 mr-1" /> Remover</>}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function OrgMembersPage() {
  const { user } = useAuth();
  const orgId = user?.current_organization?.id || "";
  const orgName = user?.current_organization?.slug || "Organização";
  const { members, isLoading, error, mutate } = useOrgMembers(orgId);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [search, setSearch] = useState("");

  const isAdmin = user?.is_system_admin || false;
  const canManage = isAdmin ||
    user?.current_organization?.role === "GERENTE" ||
    user?.current_organization?.role === "OWNER";

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError("");
    if (!newEmail) return;

    try {
      setIsSubmitting(true);
      await addOrgMember(orgId, newEmail);
      await mutate();
      setIsModalOpen(false);
      setNewEmail("");
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : "Erro ao adicionar membro");
    } finally {
      setIsSubmitting(false);
    }
  };

  const filteredMembers = (members || []).filter((m: Member) =>
    m.email.toLowerCase().includes(search.toLowerCase()) ||
    m.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div>
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-8 gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1 text-sm text-gray-500">
            <Link href="/licitacoes" className="hover:text-blue-600 transition-colors">Licitações</Link>
            <span>/</span>
            <span className="text-gray-900 font-medium">Membros da Organização</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Membros — {orgName}</h1>
          <p className="text-sm text-gray-500 mt-1">Gerencie quem tem acesso à organização e ao workflow compartilhado.</p>
        </div>

        {canManage && (
          <button
            onClick={() => setIsModalOpen(true)}
            className="flex items-center gap-2 bg-[#3d5a80] text-white px-4 py-2 rounded-lg hover:bg-[#293241] transition-colors shadow-sm font-medium"
          >
            <Plus className="w-5 h-5" />
            Adicionar membro
          </button>
        )}
      </div>

      {/* Toolbar */}
      <div className="bg-white p-4 rounded-t-lg border border-gray-200 border-b-0 flex justify-between items-center">
        <div className="relative max-w-sm w-full">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <Search className="h-5 w-5 text-gray-400" />
          </div>
          <input
            type="text"
            className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-md leading-5 bg-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
            placeholder="Buscar membros..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <Users className="w-4 h-4" />
          <span>{filteredMembers.length} membro{filteredMembers.length !== 1 ? "s" : ""}</span>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white border border-gray-200 rounded-b-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm whitespace-nowrap">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 font-semibold text-gray-900">Nome</th>
                <th className="px-6 py-3 font-semibold text-gray-900">Email</th>
                <th className="px-6 py-3 font-semibold text-gray-900">Papel</th>
                <th className="px-6 py-3 font-semibold text-gray-900">Membro desde</th>
                <th className="px-6 py-3 font-semibold text-gray-900 text-right">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {isLoading && (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-gray-500">
                    <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2 text-blue-600" />
                    Carregando membros...
                  </td>
                </tr>
              )}
              {error && (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-red-500">
                    Erro ao carregar membros.
                  </td>
                </tr>
              )}
              {!isLoading && !error && filteredMembers.map((member: Member) => (
                <MemberRow key={member.id} member={member} orgId={orgId} onMutate={mutate} canManage={canManage} isAdmin={isAdmin} />
              ))}
              {!isLoading && filteredMembers.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-gray-500">
                    Nenhum membro encontrado.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add Member Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md overflow-hidden">
            <div className="flex justify-between items-center px-6 py-4 border-b border-gray-100">
              <h3 className="text-lg font-semibold text-gray-900">Adicionar Membro</h3>
              <button onClick={() => { setIsModalOpen(false); setSubmitError(""); }} className="text-gray-400 hover:text-gray-600 transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleAdd} className="p-6">
              {submitError && (
                <div className="mb-4 p-3 bg-red-50 text-red-700 text-sm rounded-lg border border-red-100">
                  {submitError}
                </div>
              )}

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Email do usuário *
                  </label>
                  <input
                    type="email"
                    required
                    value={newEmail}
                    onChange={(e) => setNewEmail(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="usuario@email.com"
                  />
                  <p className="mt-1 text-xs text-gray-500">O usuário precisa estar cadastrado no sistema.</p>
                </div>
              </div>

              <div className="mt-8 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
                  disabled={isSubmitting}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={!newEmail || isSubmitting}
                  className="px-4 py-2 text-sm font-medium text-white bg-[#3d5a80] rounded-lg hover:bg-[#293241] disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center min-w-[100px]"
                >
                  {isSubmitting ? <Loader2 className="w-5 h-5 animate-spin" /> : "Adicionar"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
