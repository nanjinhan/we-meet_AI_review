"use client";

import { useQuery } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";

export type Store = components["schemas"]["StoreOut"];

type StoreContextValue = {
  stores: Store[];
  store: Store | null;
  setStoreId: (id: number) => void;
  isLoading: boolean;
  isError: boolean;
};

const StoreContext = createContext<StoreContextValue | null>(null);

const LS_KEY = "wm.storeId";

/** (app) 전체에서 현재 선택 매장을 공유한다. 선택은 localStorage 에 유지. */
export function StoreProvider({ children }: { children: React.ReactNode }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["stores"],
    queryFn: () => api<Store[]>("/stores"),
    retry: 1,
  });

  const stores = data ?? [];
  const [storeId, setStoreIdState] = useState<number | null>(null);

  useEffect(() => {
    const saved = Number(localStorage.getItem(LS_KEY));
    if (saved) setStoreIdState(saved);
  }, []);

  const setStoreId = (id: number) => {
    setStoreIdState(id);
    localStorage.setItem(LS_KEY, String(id));
  };

  const store = stores.find((s) => s.id === storeId) ?? stores[0] ?? null;

  return (
    <StoreContext.Provider value={{ stores, store, setStoreId, isLoading, isError }}>
      {children}
    </StoreContext.Provider>
  );
}

export function useStore() {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("useStore 는 StoreProvider 안에서만 사용");
  return ctx;
}
