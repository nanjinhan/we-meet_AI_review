"use client";

// cult-ui 의 AnimatedNumber 컴포넌트 이식 (https://www.cult-ui.com/docs/components/animated-number)
// motion 의 spring 으로 숫자가 목표값까지 굴러가며 표시된다.
import { motion, useSpring, useTransform } from "motion/react";
import { useEffect } from "react";

type Props = {
  value: number;
  /** 소수 자리수 (기본 0) */
  precision?: number;
  mass?: number;
  stiffness?: number;
  damping?: number;
  className?: string;
};

export function AnimatedNumber({
  value,
  precision = 0,
  mass = 0.8,
  stiffness = 75,
  damping = 15,
  className,
}: Props) {
  const spring = useSpring(value, { mass, stiffness, damping });
  const display = useTransform(spring, (n) =>
    n.toLocaleString("ko-KR", {
      minimumFractionDigits: precision,
      maximumFractionDigits: precision,
    }),
  );

  useEffect(() => {
    spring.set(value);
  }, [spring, value]);

  return <motion.span className={className}>{display}</motion.span>;
}
