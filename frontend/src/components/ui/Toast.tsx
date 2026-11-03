"use client";

import { createContext, useCallback, useContext, useState } from "react";

type Toast = { id: number; text: string; tone: "ok" | "error" };
const Ctx = createContext<(text: string, tone?: Toast["tone"]) => void>(() => {});

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: Toast["tone"] = "ok") => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs, { id, text, tone }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), 4500);
  }, []);
  return (
    <Ctx.Provider value={push}>
      {children}
      <div aria-live="polite" className="fixed inset-x-4 bottom-20 z-50 flex flex-col items-center gap-2 md:bottom-6">
        {items.map((t) => (
          <div
            key={t.id}
            role="status"
            className={`max-w-md rounded-lg border px-4 py-2.5 text-sm shadow-lg ${
              t.tone === "error"
                ? "border-danger/50 bg-[#2a1614] text-[#ffd9d4]"
                : "border-gold/40 bg-raised text-text"
            }`}
          >
            {t.text}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx);
