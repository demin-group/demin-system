"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function LoginForm() {
  const params = useSearchParams();
  const error = params.get("error");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    const supabase = createClient();
    const { error: signInError } = await supabase.auth.signInWithOtp({
      email,
      options: {
        emailRedirectTo: `${window.location.origin}/auth/callback`,
      },
    });
    setLoading(false);
    if (signInError) {
      toast.error(signInError.message);
      return;
    }
    setSent(true);
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-background">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-2xl">DEMIN Dashboard</CardTitle>
          <CardDescription>
            Inicia sesión con tu email autorizado. Te enviaremos un magic link.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error === "unauthorized" && (
            <div className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
              Email no autorizado. Solicita acceso al administrador.
            </div>
          )}
          {error === "auth_failed" && (
            <div className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
              No hemos podido validar el magic link. Solicita uno nuevo.
            </div>
          )}
          {sent ? (
            <div className="space-y-2 text-sm">
              <p className="font-medium">Revisa tu email.</p>
              <p className="text-muted-foreground">
                Te hemos enviado un magic link a{" "}
                <span className="font-medium text-foreground">{email}</span>.
                Haz click en el enlace del correo para entrar.
              </p>
            </div>
          ) : (
            <form onSubmit={onSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="tucorreo@dominio.com"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  disabled={loading}
                />
              </div>
              <Button
                type="submit"
                className="w-full"
                disabled={loading || !email}
              >
                {loading ? "Enviando…" : "Enviar magic link"}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
