"use client";

import { useMutation } from "@tanstack/react-query";
import { Gamepad2, KeyRound, Lock, Shield, User } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { loginOperator } from "@/lib/api";
import { saveSession, useRedirectIfLoggedIn } from "@/lib/auth";

export default function LoginPage() {
  useRedirectIfLoggedIn();
  const router = useRouter();
  const [loginName, setLoginName] = useState("");
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!loginName.trim()) throw new Error("请填登录名");
      if (!password) throw new Error("请填密码");
      if (totpCode.length !== 6 || !/^\d{6}$/.test(totpCode)) {
        throw new Error("请填 6 位 TOTP 验证码");
      }
      return loginOperator({
        loginName: loginName.trim(),
        password,
        totpCode
      });
    },
    onSuccess: (data) => {
      saveSession(data.token, data.operator);
      router.replace("/");
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "登录失败,请检查三要素")
  });

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <Card className="w-full max-w-md">
        <CardHeader className="items-center text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <Gamepad2 className="h-7 w-7" aria-hidden="true" />
          </div>
          <CardTitle className="text-xl">XBOX 客服销售系统</CardTitle>
          <div className="text-xs text-muted-foreground">
            登录三要素 = 账号 + 密码 + 6 位 TOTP
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1">
            <label className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
              <User className="h-3 w-3" />
              登录名
            </label>
            <Input
              value={loginName}
              onChange={(e) => setLoginName(e.target.value)}
              placeholder="如 zhang_san"
              autoFocus
            />
          </div>
          <div className="space-y-1">
            <label className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
              <Lock className="h-3 w-3" />
              密码
            </label>
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="≥ 6 位"
            />
          </div>
          <div className="space-y-1">
            <label className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
              <Shield className="h-3 w-3" />
              TOTP 验证码 (Google Authenticator / Authy)
            </label>
            <Input
              type="text"
              inputMode="numeric"
              maxLength={6}
              value={totpCode}
              onChange={(e) =>
                setTotpCode(e.target.value.replace(/\D/g, "").slice(0, 6))
              }
              placeholder="6 位数字"
              className="text-center font-mono text-lg tracking-widest"
            />
          </div>

          {error ? (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              {error}
            </div>
          ) : null}

          <Button
            className="w-full"
            size="lg"
            onClick={() => {
              setError(null);
              mutation.mutate();
            }}
            disabled={mutation.isPending}
          >
            <KeyRound className="h-4 w-4" />
            {mutation.isPending ? "登录中…" : "登录"}
          </Button>

          <div className="rounded-md bg-muted px-3 py-2 text-[10px] leading-relaxed text-muted-foreground">
            首次登录需先在 CEO 后台扫码绑定 TOTP，否则会提示"二步验证未绑定"。
            <br />
            忘记 TOTP 二维码请联系 CEO 在「客服管理」页重看。
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
