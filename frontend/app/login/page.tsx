"use client";

import { useState, FormEvent, useEffect } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import Link from "next/link";
import { Eye, EyeOff } from "lucide-react";
import { apiFetch, setAccessToken } from "@/lib/apiClient";

export default function LoginPage() {
  const router = useRouter();
  const [isRegisterMode, setIsRegisterMode] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [allowRegister, setAllowRegister] = useState(true);
  const [offlineError, setOfflineError] = useState("");

  // Check if register is allowed (using a simple health/info endpoint if it existed, or env. For now we assume allowed unless explicitly false)
  useEffect(() => {
    // If you exposed a NEXT_PUBLIC_AUTH_ALLOW_REGISTER variable, you could use it here.
    if (process.env.NEXT_PUBLIC_AUTH_ALLOW_REGISTER === "false") {
      setAllowRegister(false);
    }
    
    const checkHealth = async () => {
      try {
        // Use relative URL — Next.js proxy handles routing to the backend
        const res = await fetch('/api/health', {
          credentials: "include"
        });
        if (!res.ok) throw new Error("Backend not ok");
        setOfflineError("");
      } catch {
        setOfflineError("Backend não acessível. Verifique se o FastAPI está rodando e se a porta 8000 está exposta.");
      }
    };
    checkHealth();
  }, []);

  const validatePassword = (pass: string) => {
    if (pass.length < 10) return "A senha deve ter pelo menos 10 caracteres.";
    if (!/[A-Za-z]/.test(pass)) return "A senha deve conter pelo menos uma letra.";
    if (!/\d/.test(pass)) return "A senha deve conter pelo menos um número.";
    return null;
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!email || !password) return;

    if (isRegisterMode) {
      if (password !== confirmPassword) {
        setError("As senhas não coincidem.");
        return;
      }
      const passError = validatePassword(password);
      if (passError) {
        setError(passError);
        return;
      }
    }

    setError("");
    setLoading(true);

    try {
      if (isRegisterMode) {
        // Registro
        const regRes = await apiFetch("/api/auth/register", {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
        
        if (!regRes.ok) {
          const text = await regRes.text();
          if (process.env.NODE_ENV === "development") {
            console.log("Register error status: ", regRes.status, text);
          }
          let detail = "Erro ao registrar. O email pode já estar em uso.";
          try {
             const data = JSON.parse(text);
             detail = data.detail || detail;
          } catch {}
          setError(detail);
          setLoading(false);
          return;
        }
      }

      // Login (tanto para login direto quanto pós-registro de sucesso)
      const res = await apiFetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email,
          password: password,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setAccessToken(data.access_token);
        router.push("/");
      } else {
        const text = await res.text();
        if (process.env.NODE_ENV === "development") {
            console.log("Login error status: ", res.status, text);
        }
        let detail = "Credenciais inválidas. Tente novamente.";
        try {
            const data = JSON.parse(text);
            detail = data.detail || detail;
        } catch {}
        setError(detail);
      }
    } catch (err) {
      if (process.env.NODE_ENV === "development") {
          console.error("Fetch error:", err);
      }
      setError("Falha de comunicação com o servidor (CORS ou backend offline)");
    } finally {
      setLoading(false);
    }
  };

  const isFormValid = isRegisterMode 
    ? email.trim() !== "" && password.trim() !== "" && confirmPassword.trim() !== "" 
    : email.trim() !== "" && password.trim() !== "";

  return (
    <div 
      className="min-h-screen w-full flex flex-col items-center justify-center p-4 bg-cover bg-center bg-no-repeat relative"
      style={{ backgroundImage: "url('/login_entscheid.png')" }}
    >
      {/* Light overlay just in case the image is too bright, strictly optional depending on the image. 
          The user mentioned "overlay leve mantendo a imagem visível" if necessary. */}
      <div className="absolute inset-0 bg-white/10 backdrop-blur-[2px] pointer-events-none" />
      
      <div className="relative z-10 flex flex-col items-center w-full max-w-sm">
        
        {/* LOGO */}
        <div className="mb-10 w-full flex justify-center">
            <Image
              src="/entscheid.png"
              alt="Entscheid Logo"
              width={280}
              height={80}
              className="w-[220px] sm:w-[280px] max-w-[80%] object-contain"
              priority
            />
        </div>

        <form onSubmit={handleSubmit} className="w-full flex flex-col gap-4">
          
          {offlineError && (
            <div className="w-full p-3 bg-orange-100/90 border border-orange-200 text-orange-800 text-sm rounded-lg text-center backdrop-blur-sm shadow-sm transition-all font-medium">
              {offlineError}
            </div>
          )}

          {error && (
            <div className="w-full p-3 bg-red-100/90 border border-red-200 text-red-700 text-sm rounded-lg text-center backdrop-blur-sm shadow-sm transition-all">
              {error}
            </div>
          )}

          {/* CAMPOS */}
          <div className="flex flex-col gap-3">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="E-mail"
              className="w-full px-4 py-3 bg-white/90 backdrop-blur-md border border-gray-200 rounded-xl text-[#293241] placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-[#3d5a80] focus:border-transparent transition-all shadow-sm"
              disabled={loading}
              required
            />
            
            <div className="relative w-full">
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Senha"
                className="w-full px-4 py-3 pr-12 bg-white/90 backdrop-blur-md border border-gray-200 rounded-xl text-[#293241] placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-[#3d5a80] focus:border-transparent transition-all shadow-sm"
                disabled={loading}
                required
              />
              <button
                type="button"
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700 focus:outline-none p-1"
                onClick={() => setShowPassword(!showPassword)}
                tabIndex={-1}
              >
                {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
              </button>
            </div>

            {isRegisterMode && (
              <div className="relative w-full">
                <input
                  type={showConfirmPassword ? "text" : "password"}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Confirmar Senha"
                  className="w-full px-4 py-3 pr-12 bg-white/90 backdrop-blur-md border border-gray-200 rounded-xl text-[#293241] placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-[#3d5a80] focus:border-transparent transition-all shadow-sm"
                  disabled={loading}
                  required
                />
                <button
                  type="button"
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700 focus:outline-none p-1"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  tabIndex={-1}
                >
                  {showConfirmPassword ? <EyeOff size={20} /> : <Eye size={20} />}
                </button>
              </div>
            )}
          </div>

          {/* BOTÕES */}
          <div className="flex flex-col gap-3 mt-4">
            <button
              type="submit"
              disabled={!isFormValid || loading}
              className="w-full py-3.5 px-4 bg-[#3d5a80] text-white font-medium rounded-full hover:bg-[#293241] disabled:opacity-60 disabled:cursor-not-allowed transition-all shadow-md flex items-center justify-center"
            >
              {loading ? (
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                isRegisterMode ? "Criar Conta" : "Login"
              )}
            </button>
            
            {!isRegisterMode && allowRegister && (
              <button
                type="button"
                onClick={() => {
                  setError("");
                  setIsRegisterMode(true);
                }}
                disabled={loading}
                className="w-full py-3.5 px-4 bg-transparent border-2 border-[#3d5a80] text-[#3d5a80] font-medium rounded-full hover:bg-[#e0fbfc] hover:text-[#293241] disabled:opacity-60 disabled:cursor-not-allowed transition-all"
              >
                Registrar-se
              </button>
            )}

            {!isRegisterMode && (
              <div className="mt-2 text-center w-full">
                  <Link 
                      href="/forgot-password" 
                      className="text-sm border-0 font-medium text-white/90 hover:text-white underline-offset-4 hover:underline transition-all drop-shadow-md bg-transparent filter mix-blend-difference pb-2"
                  >
                      Esqueci minha senha
                  </Link>
              </div>
            )}
            
            {isRegisterMode && (
              <button
                type="button"
                onClick={() => {
                  setError("");
                  setIsRegisterMode(false);
                }}
                disabled={loading}
                className="w-full py-3.5 px-4 bg-transparent border-2 border-transparent text-[#3d5a80] hover:text-[#293241] font-medium rounded-full hover:bg-black/5 disabled:opacity-60 disabled:cursor-not-allowed transition-all"
              >
                Voltar para Login
              </button>
            )}

            {!allowRegister && !isRegisterMode && (
              <p className="text-center text-xs text-[#293241]/70 mt-2">
                Cadastros desabilitados. Contate o administrador.
              </p>
            )}
          </div>

        </form>
      </div>
    </div>
  );
}
