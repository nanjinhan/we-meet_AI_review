"use client";

import { motion } from "motion/react";
import { cn } from "@/lib/utils";

/** 섹션 진입 애니메이션 래퍼 — cult-ui 스타일의 은은한 fade + rise. */
export function FadeIn({
  children,
  delay = 0,
  className,
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay, ease: "easeOut" }}
      className={cn(className)}
    >
      {children}
    </motion.div>
  );
}
