export default function SettingsPage() {
  return (
    <section>
      <h1 className="text-xl font-bold">설정</h1>
      <p className="mt-2 text-sm text-gray-500">
        톤 프로필·알림 설정 (T-F 이후). API: <code>PUT /stores/&#123;id&#125;/settings</code>
      </p>
    </section>
  );
}
