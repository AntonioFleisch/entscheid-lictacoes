"use client";

import { useState } from "react";
import { Plus, Search, Building2, X, Loader2 } from "lucide-react";
import Link from "next/link";
import { useAdminOrgs } from "@/lib/hooks";

interface Organization {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
  created_at: string;
}

import { updateOrganization, deleteOrganization, createOrganization, setOrgManager } from "@/lib/api";

function slugify(text: string) {
  return text
    .toString()
    .toLowerCase()
    .trim()
    .replace(/\s+/g, '-')
    .replace(/[^\w\-]+/g, '')
    .replace(/\-\-+/g, '-')
    .replace(/^-+/, '')
    .replace(/-+$/, '');
}

// Subcomponent for each row to manage its own editing/deleting state
function OrgRow({ org, onMutate }: { org: Organization, onMutate: () => Promise<void> }) {
  const [isEditing, setIsEditing] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isSettingManager, setIsSettingManager] = useState(false);
  
  const [editName, setEditName] = useState(org.name || "");
  const [editSlug, setEditSlug] = useState(org.slug || "");
  const [editIsActive, setEditIsActive] = useState(org.is_active);
  const [managerEmail, setManagerEmail] = useState("");
  
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  const handleEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!editName || !editSlug) return;
    
    try {
      setIsSubmitting(true);
      await updateOrganization(org.id, editName, editSlug, editIsActive);
      await onMutate();
      setIsEditing(false);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Erro ao editar");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async () => {
    setError("");
    try {
      setIsSubmitting(true);
      await deleteOrganization(org.id);
      await onMutate();
      setIsDeleting(false);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Erro ao deletar");
      }
      setIsSubmitting(false);
    }
  };

  return (
    <>
      <tr className="hover:bg-gray-50 transition-colors group">
        <td className="px-6 py-4">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-md ${org.is_active ? 'bg-blue-50 text-blue-600' : 'bg-gray-100 text-gray-500'}`}>
              <Building2 className="w-4 h-4" />
            </div>
            <span className={`font-medium ${org.is_active ? 'text-gray-900' : 'text-gray-500 line-through decoration-gray-300'}`}>{org.name}</span>
          </div>
        </td>
        <td className="px-6 py-4 text-gray-500 font-mono text-xs">{org.slug}</td>
        <td className="px-6 py-4">
          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${org.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'}`}>
            {org.is_active ? 'Ativa' : 'Inativa'}
          </span>
        </td>
        <td className="px-6 py-4 text-gray-500">{new Date(org.created_at).toLocaleDateString()}</td>
        <td className="px-6 py-4 text-right">
          <div className="flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
            <button 
              onClick={() => setIsSettingManager(true)}
              className="text-gray-400 hover:text-green-600 transition-colors p-1.5 rounded-md hover:bg-green-50 text-sm font-medium"
            >
              Gerente
            </button>
            <button 
              onClick={() => setIsEditing(true)}
              className="text-gray-400 hover:text-blue-600 transition-colors p-1.5 rounded-md hover:bg-blue-50 text-sm font-medium"
            >
              Editar
            </button>
            {org.slug !== 'default' && (
              <button 
                onClick={() => setIsDeleting(true)}
                className="text-gray-400 hover:text-red-600 transition-colors p-1.5 rounded-md hover:bg-red-50 text-sm font-medium"
              >
                Remover
              </button>
            )}
          </div>

          {/* Edit Modal */}
          {isEditing && (
            <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
              <div className="bg-white rounded-xl shadow-xl w-full max-w-md overflow-hidden">
                <div className="flex justify-between items-center px-6 py-4 border-b border-gray-100">
                  <h3 className="text-lg font-semibold text-gray-900">Editar Organização</h3>
                  <button onClick={() => { setIsEditing(false); setError(""); }} className="text-gray-400 hover:text-gray-600">
                    <X className="w-5 h-5" />
                  </button>
                </div>
                <form onSubmit={handleEdit} className="p-6">
                  {error && <div className="mb-4 p-3 bg-red-50 text-red-700 text-sm rounded-lg">{error}</div>}
                  <div className="space-y-4 text-left">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Nome</label>
                      <input type="text" required value={editName || ""} onChange={e => {
                        setEditName(e.target.value);
                        if (slugify(editName) === editSlug) setEditSlug(slugify(e.target.value));
                      }} className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500" />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Slug</label>
                      <input type="text" required value={editSlug || ""} onChange={e => setEditSlug(slugify(e.target.value))} className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 font-mono text-sm" />
                    </div>
                    <div className="flex items-center gap-2 mt-4">
                      <input type="checkbox" id={`active-${org.id}`} checked={editIsActive} onChange={e => setEditIsActive(e.target.checked)} className="rounded text-blue-600 focus:ring-blue-500" disabled={org.slug === 'default'} />
                      <label htmlFor={`active-${org.id}`} className="text-sm font-medium text-gray-700">Organização Ativa</label>
                    </div>
                  </div>
                  <div className="mt-8 flex justify-end gap-3">
                    <button type="button" onClick={() => setIsEditing(false)} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border rounded-lg hover:bg-gray-50" disabled={isSubmitting}>Cancelar</button>
                    <button type="submit" disabled={isSubmitting} className="px-4 py-2 text-sm font-medium text-white bg-[#3d5a80] rounded-lg hover:bg-[#293241] flex items-center min-w-[100px] justify-center">
                      {isSubmitting ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Salvar'}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}

          {/* Delete Confirmation Modal */}
          {isDeleting && (
            <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
              <div className="bg-white rounded-xl shadow-xl w-full max-w-md overflow-hidden p-6 z-50">
                <h3 className="text-xl font-bold text-gray-900 mb-2 whitespace-normal text-left">Desativar {org.name}?</h3>
                <p className="text-gray-600 mb-6 whitespace-normal text-left">Isso irá marcar a organização como inativa. Usuários associados a ela perderão o acesso ao painel do sistema.</p>
                {error && <div className="mb-4 p-3 bg-red-50 text-red-700 text-sm rounded-lg whitespace-normal text-left">{error}</div>}
                <div className="flex justify-end gap-3">
                  <button type="button" onClick={() => setIsDeleting(false)} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border rounded-lg hover:bg-gray-50" disabled={isSubmitting}>Cancelar</button>
                  <button onClick={handleDelete} disabled={isSubmitting} className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 flex items-center justify-center min-w-[100px]">
                    {isSubmitting ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Desativar'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Set Manager Modal */}
          {isSettingManager && (
            <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
              <div className="bg-white rounded-xl shadow-xl w-full max-w-md overflow-hidden">
                <div className="flex justify-between items-center px-6 py-4 border-b border-gray-100">
                  <h3 className="text-lg font-semibold text-gray-900">Definir Gerente — {org.name}</h3>
                  <button onClick={() => { setIsSettingManager(false); setError(""); setManagerEmail(""); }} className="text-gray-400 hover:text-gray-600">
                    <X className="w-5 h-5" />
                  </button>
                </div>
                <form onSubmit={async (e) => {
                  e.preventDefault();
                  setError("");
                  if (!managerEmail) return;
                  try {
                    setIsSubmitting(true);
                    await setOrgManager(org.id, managerEmail);
                    await onMutate();
                    setIsSettingManager(false);
                    setManagerEmail("");
                  } catch (err: unknown) {
                    setError(err instanceof Error ? err.message : "Erro ao definir gerente");
                  } finally {
                    setIsSubmitting(false);
                  }
                }} className="p-6">
                  {error && <div className="mb-4 p-3 bg-red-50 text-red-700 text-sm rounded-lg">{error}</div>}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Email do usuário *</label>
                    <input type="email" required value={managerEmail} onChange={e => setManagerEmail(e.target.value)} className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500" placeholder="usuario@email.com" />
                    <p className="mt-1 text-xs text-gray-500">O usuário será adicionado (ou promovido) como Gerente desta organização.</p>
                  </div>
                  <div className="mt-8 flex justify-end gap-3">
                    <button type="button" onClick={() => setIsSettingManager(false)} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border rounded-lg hover:bg-gray-50" disabled={isSubmitting}>Cancelar</button>
                    <button type="submit" disabled={!managerEmail || isSubmitting} className="px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-lg hover:bg-green-700 disabled:opacity-50 flex items-center justify-center min-w-[100px]">
                      {isSubmitting ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Definir Gerente'}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}
        </td>
      </tr>
    </>
  );
}

export default function OrganizationsPage() {
  const [search, setSearch] = useState("");
  const { organizations, isLoading, error, mutate } = useAdminOrgs();

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newSlug, setNewSlug] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");

  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setNewName(val);
    if (!newSlug || slugify(newName) === newSlug) {
      setNewSlug(slugify(val));
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError("");
    
    if (!newName || !newSlug) return;
    if (newSlug.length < 2) {
      setSubmitError("Slug deve ter pelo menos 2 caracteres.");
      return;
    }

    try {
      setIsSubmitting(true);
      await createOrganization(newName, newSlug);
      await mutate();
      setIsModalOpen(false);
      setNewName("");
      setNewSlug("");
    } catch (err: unknown) {
      if (err instanceof Error) {
        setSubmitError(err.message);
      } else {
        setSubmitError("Erro ao criar organização");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const filteredOrgs = organizations.filter((org: Organization) => 
    org.name.toLowerCase().includes(search.toLowerCase()) || 
    org.slug.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div>
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-8 gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1 text-sm text-gray-500">
            <Link href="/admin" className="hover:text-blue-600 transition-colors">Admin</Link>
            <span>/</span>
            <span className="text-gray-900 font-medium">Organizations</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Organizations</h1>
        </div>
        
        <button 
          onClick={() => setIsModalOpen(true)}
          className="flex items-center gap-2 bg-[#3d5a80] text-white px-4 py-2 rounded-lg hover:bg-[#293241] transition-colors shadow-sm font-medium"
        >
          <Plus className="w-5 h-5" />
          Registrar organização
        </button>
      </div>

      {/* Toolbar */}
      <div className="bg-white p-4 rounded-t-lg border border-gray-200 border-b-0 flex justify-between items-center">
        <div className="relative max-w-sm w-full">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <Search className="h-5 w-5 text-gray-400" />
          </div>
          <input
            type="text"
            className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-md leading-5 bg-white placeholder-gray-500 focus:outline-none focus:placeholder-gray-400 focus:ring-1 focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
            placeholder="Search organizations..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {/* Table */}
      <div className="bg-white border border-gray-200 rounded-b-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm whitespace-nowrap">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 font-semibold text-gray-900">Organization Name</th>
                <th className="px-6 py-3 font-semibold text-gray-900">Slug</th>
                <th className="px-6 py-3 font-semibold text-gray-900">Status</th>
                <th className="px-6 py-3 font-semibold text-gray-900">Created At</th>
                <th className="px-6 py-3 font-semibold text-gray-900 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {isLoading && (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-gray-500">
                    <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2 text-blue-600" />
                    Carregando organizações...
                  </td>
                </tr>
              )}
              {error && (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-red-500">
                    Erro ao carregar organizações.
                  </td>
                </tr>
              )}
              {!isLoading && !error && filteredOrgs.map((org: Organization) => (
                <OrgRow key={org.id} org={org} onMutate={mutate} />
              ))}
              
              {!isLoading && filteredOrgs.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-gray-500">
                    Nenhuma organização cadastrada.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      
      {/* Create Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md overflow-hidden">
            <div className="flex justify-between items-center px-6 py-4 border-b border-gray-100">
              <h3 className="text-lg font-semibold text-gray-900">Registrar Organização</h3>
              <button onClick={() => setIsModalOpen(false)} className="text-gray-400 hover:text-gray-600 transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <form onSubmit={handleCreate} className="p-6">
              {submitError && (
                <div className="mb-4 p-3 bg-red-50 text-red-700 text-sm rounded-lg border border-red-100">
                  {submitError}
                </div>
              )}
              
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Nome da organização *
                  </label>
                  <input
                    type="text"
                    required
                    value={newName}
                    onChange={handleNameChange}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="Ex: Empresa XPTO"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Slug *
                  </label>
                  <input
                    type="text"
                    required
                    value={newSlug}
                    onChange={(e) => setNewSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm text-gray-600"
                    placeholder="empresa-xpto"
                  />
                  <p className="mt-1 text-xs text-gray-500">O slug será usado em URLs e configurações (somente letras, números e hífens).</p>
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
                  disabled={!newName || !newSlug || isSubmitting}
                  className="px-4 py-2 text-sm font-medium text-white bg-[#3d5a80] rounded-lg hover:bg-[#293241] disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center min-w-[100px]"
                >
                  {isSubmitting ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Salvar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
