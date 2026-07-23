import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** shadcn/cult-ui 공통 클래스 병합 유틸. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
