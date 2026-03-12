"use client";

import { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Lock, ArrowLeft, Loader2, Eye, EyeOff, CheckCircle2 } from "lucide-react";
import { apiFetch } from "@/lib/apiClient";

export default function ResetPasswordPage() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const token = searchParams.get("token");

    const [password, setPassword] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    const [showPassword, setShowPassword] = useState(false);
    const [showConfirmPassword, setShowConfirmPassword] = useState(false);

    const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
    const [errorMessage, setErrorMessage] = useState("");

    // Missing token guard
    useEffect(() => {
        if (!token) {
            setStatus("error");
            setErrorMessage("Link de recuperação inválido ou ausente.");
        }
    }, [token]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        
        if (password !== confirmPassword) {
            setStatus("error");
            setErrorMessage("As senhas não coincidem.");
            return;
        }

        if (password.length < 10) {
            setStatus("error");
            setErrorMessage("A senha deve ter pelo menos 10 caracteres.");
            return;
        }

        setStatus("loading");
        setErrorMessage("");

        try {
            const res = await apiFetch("/api/auth/reset-password", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ token, new_password: password }),
            });

            if (!res.ok) {
                const data = await res.json();
                throw new Error(data.detail || "Falha ao redefinir a senha.");
            }

            setStatus("success");
            
            // Redirect to login after 3 seconds
            setTimeout(() => {
                router.push("/login?reset=success");
            }, 3000);

        } catch (err) {
             console.error("Reset password error:", err);
             setStatus("error");
             if (err instanceof Error) {
                 setErrorMessage(err.message || "Ocorreu um erro ao processar sua solicitação. O link pode ter expirado.");
             } else {
                 setErrorMessage("Ocorreu um erro ao processar sua solicitação. O link pode ter expirado.");
             }
        }
    };

    if (!token && status === "error") {
        return (
            <div className="min-h-screen bg-gray-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
                <div className="sm:mx-auto sm:w-full sm:max-w-md">
                    <div className="bg-white py-8 px-4 shadow-xl sm:rounded-2xl sm:px-10 border border-gray-100 text-center">
                        <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-red-100 mb-4">
                            <span className="text-red-500 font-bold text-xl">!</span>
                        </div>
                        <h3 className="text-lg font-medium text-gray-900 mb-2">Link Inválido</h3>
                        <p className="text-sm text-gray-500 mb-6">{errorMessage}</p>
                        <Link href="/forgot-password" className="text-sm font-medium text-primary hover:text-ink transition-colors">
                            Solicitar novo link
                        </Link>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
            <div className="sm:mx-auto sm:w-full sm:max-w-md">
                <div className="flex justify-center mb-6 text-primary">
                     <Lock size={48} />
                </div>
                <h2 className="mt-2 text-center text-3xl font-extrabold text-gray-900 tracking-tight">
                    Criar Nova Senha
                </h2>
                <p className="mt-2 text-center text-sm text-gray-600">
                    Defina uma nova senha segura para sua conta.
                </p>
            </div>

            <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
                <div className="bg-white py-8 px-4 shadow-xl sm:rounded-2xl sm:px-10 border border-gray-100 relative overflow-hidden">
                    <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-primary to-secondary"></div>

                    {status === "success" ? (
                        <div className="text-center py-4">
                            <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-green-100 mb-4">
                                <CheckCircle2 className="h-6 w-6 text-green-600" />
                            </div>
                            <h3 className="text-lg font-medium text-gray-900 mb-2">Senha Atualizada!</h3>
                            <p className="text-sm text-gray-500 mb-6">
                                Sua senha foi redefinida com sucesso. Redirecionando para o login...
                            </p>
                            <Loader2 className="animate-spin text-primary mx-auto" size={24} />
                        </div>
                    ) : (
                        <form className="space-y-5" onSubmit={handleSubmit}>
                            {/* Password input */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700">Nova Senha</label>
                                <div className="mt-1 relative rounded-md shadow-sm">
                                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                        <Lock className="h-5 w-5 text-gray-400" />
                                    </div>
                                    <input
                                        type={showPassword ? "text" : "password"}
                                        required
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        className="appearance-none block w-full pl-10 pr-10 px-3 py-2.5 border border-gray-300 rounded-lg placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary sm:text-sm text-gray-900"
                                        placeholder="Mínimo de 10 caracteres"
                                        minLength={10}
                                        disabled={status === "loading"}
                                    />
                                    <button
                                        type="button"
                                        className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600"
                                        onClick={() => setShowPassword(!showPassword)}
                                        tabIndex={-1}
                                    >
                                        {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                                    </button>
                                </div>
                            </div>

                            {/* Confirm Password input */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700">Confirmar Nova Senha</label>
                                <div className="mt-1 relative rounded-md shadow-sm">
                                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                        <Lock className="h-5 w-5 text-gray-400" />
                                    </div>
                                    <input
                                        type={showConfirmPassword ? "text" : "password"}
                                        required
                                        value={confirmPassword}
                                        onChange={(e) => setConfirmPassword(e.target.value)}
                                        className="appearance-none block w-full pl-10 pr-10 px-3 py-2.5 border border-gray-300 rounded-lg placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary sm:text-sm text-gray-900"
                                        placeholder="Repita a senha"
                                        minLength={10}
                                        disabled={status === "loading"}
                                    />
                                    <button
                                        type="button"
                                        className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600"
                                        onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                                        tabIndex={-1}
                                    >
                                        {showConfirmPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                                    </button>
                                </div>
                            </div>

                            {status === "error" && (
                                <div className="rounded-md bg-red-50 p-3 border border-red-100">
                                    <p className="text-sm text-red-700">{errorMessage}</p>
                                </div>
                            )}

                            <div className="pt-2">
                                <button
                                    type="submit"
                                    disabled={status === "loading" || !password || !confirmPassword}
                                    className="w-full flex justify-center py-2.5 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-primary hover:bg-ink focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary transition-colors disabled:opacity-70 disabled:cursor-not-allowed"
                                >
                                    {status === "loading" ? (
                                        <span className="flex items-center gap-2">
                                            <Loader2 className="animate-spin" size={16} /> Salvando...
                                        </span>
                                    ) : (
                                        "Redefinir Senha"
                                    )}
                                </button>
                            </div>
                            
                            <div className="text-center mt-4 pt-4 border-t border-gray-50">
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
