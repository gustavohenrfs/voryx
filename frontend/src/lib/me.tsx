"use client";

import { createContext, useContext } from "react";
import type { User } from "./types";

export const MeCtx = createContext<User | null>(null);
export const useMe = () => useContext(MeCtx);
