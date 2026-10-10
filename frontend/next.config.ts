import type { NextConfig } from "next";
import withSerwist from "@serwist/next";

const nextConfig: NextConfig = {};

// T-F6: Serwist(PWA) 래핑 — manifest 설치 + 웹푸시 수신용(오프라인 캐싱은 목적 아님).
// 개발 모드에서는 끈다: SW 캐시가 `next dev`의 HMR/리프레시와 충돌한다(FRONTEND.md §1, §6).
export default withSerwist({
  swSrc: "src/app/sw.ts",
  swDest: "public/sw.js",
  disable: process.env.NODE_ENV === "development",
})(nextConfig);
