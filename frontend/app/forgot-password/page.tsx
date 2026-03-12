"use client";

import { useState } from "react";
import Link from "next/link";
import { Mail, ArrowLeft, Loader2 } from "lucide-react";
import { apiFetch } from "@/lib/apiClient";

export default function ForgotPasswordPage() {
    const [email, setEmail] = useState("");
    const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
    const [errorMessage, setErrorMessage] = useState("");

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setStatus("loading");
        setErrorMessage("");

        try {
            const res = await apiFetch("/api/auth/forgot-password", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email }),
            });

            if (res.status === 429) {
                setStatus("error");
                setErrorMessage("Muitas tentativas. Tente novamente mais tarde.");
                return;
            }

            // Backend always returns 202 for security
            setStatus("success");
        } catch (err) {
             console.error("Forgot password error:", err);
             setStatus("error");
             setErrorMessage("Ocorreu um erro ao processar sua solicitação.");
        }
    };

    return (
        <div className="min-h-screen bg-gray-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
            <div className="sm:mx-auto sm:w-full sm:max-w-md">
                <div className="flex justify-center mb-6 text-primary">
                     <Mail size={48} />
                </div>
                <h2 className="mt-2 text-center text-3xl font-extrabold text-gray-900 tracking-tight">
                    Recuperar Senha
                </h2>
                <p className="mt-2 text-center text-sm text-gray-600">
                    Digite seu email e enviaremos um link para criar uma nova senha.
                </p>
            </div>

            <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
                <div className="bg-white py-8 px-4 shadow-xl sm:rounded-2xl sm:px-10 border border-gray-100 relative overflow-hidden">
                    <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-primary to-secondary"></div>

                    {status === "success" ? (
                        <div className="text-center py-4">
                            <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-green-100 mb-4">
                                <svg className="h-6 w-6 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                                </svg>
                            </div>
                            <h3 className="text-lg font-medium text-gray-900 mb-2">Email Enviado!</h3>
                            <p className="text-sm text-gray-500 mb-6">
                                Se o email <strong>{email}</strong> estiver cadastrado, você receberá um link de recuperação em alguns minutos.
                            </p>
                            <Link href="/login" className="text-sm font-medium text-primary hover:text-ink transition-colors flex items-center justify-center gap-2">
                                <ArrowLeft size={16} /> Voltar para o Login
                            </Link>
                        </div>
                    ) : (
                        <form className="space-y-6" onSubmit={handleSubmit}>
                            <div>
                                <label htmlFor="email" className="block text-sm font-medium text-gray-700">
                                    Email
                                </label>
                                <div className="mt-1 relative rounded-md shadow-sm">
                                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                        <Mail className="h-5 w-5 text-gray-400" />
                                    </div>
                                    <input
                                        id="email"
                                        name="email"
                                        type="email"
                                        autoComplete="email"
                                        required
                                        value={email}
                                        onChange={(e) => setEmail(e.target.value)}
                                        className="appearance-none block w-full pl-10 px-3 py-2.5 border border-gray-300 rounded-lg placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary sm:text-sm text-gray-900"
                                        placeholder="seu@email.com"
                                        disabled={status === "loading"}
                                    />
                                </div>
                            </div>

                            {status === "error" && (
                                <div className="rounded-md bg-red-50 p-4 border border-red-100">
                                    <div className="flex">
                                        <div className="ml-3">
                                            <h3 className="text-sm font-medium text-red-800">Erro na solicitação</h3>
                                            <div className="mt-2 text-sm text-red-700">
                                                <p>{errorMessage}</p>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}

                            <div>
                                <button
                                    type="submit"
                                    disabled={status === "loading" || !email}
                                    className="w-full flex justify-center py-2.5 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-primary hover:bg-ink focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary transition-colors disabled:opacity-70 disabled:cursor-not-allowed"
                                >
                                    {status === "loading" ? (
                                        <span className="flex items-center gap-2">
                                            <Loader2 className="animate-spin" size={16} /> Processando...
                                        </span>
                                    ) : (
                                        "Enviar Link de Recuperação"
                                    )}
                                </button>
                            </div>
                            
                            <div className="text-center mt-4">
                                <Link href="/login" className="text-sm font-medium text-gray-600 hover:text-primary transition-colors inline-flex items-center gap-2">
                                    <ArrowLeft size={14} /> Voltar para o Login
                                </Link>
                            </div>
                        </form>
                    )}
                </div>
            </div>
        </div>
    );
}
