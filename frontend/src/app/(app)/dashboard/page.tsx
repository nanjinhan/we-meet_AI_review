export default function DashboardPage() {
  return (
    <section>
      <h1 className="text-xl font-bold">대시보드</h1>
      <p className="mt-2 text-sm text-gray-500">
        종합 점수·추세·aspect 차트 (T-F4에서 구현). API: <code>GET /dashboard?range=4w</code>
      </p>
    </section>
  );
}
