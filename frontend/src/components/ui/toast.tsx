"use client";

import * as React from "react";
import { toast as sonner } from "sonner";
import { Toaster } from "@/components/ui/sonner";

type ToastInput = { title: string; description?: string; tone?: "success" | "error" | "info" };

/** App-wide toasts (sonner). Kept as a hook so pages call `toast({ title, description, tone })`. */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  return (
    <>
      {children}
      <Toaster position="bottom-right" />
    </>
  );
}

function show({ title, description, tone }: ToastInput) {
  const fn = tone === "error" ? sonner.error : tone === "success" ? sonner.success : sonner.message;
  fn(title, { description });
}

export function useToast() {
  return show;
}
