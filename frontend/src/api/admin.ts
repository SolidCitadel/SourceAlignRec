// api-contract/admin.md 정합. operator 전용 읽기 대시보드. mock 분기 미도입 — backend 연결 필수.
// 파이프라인 *실행* 트리거는 미구현(별도 plan) — 본 모듈은 GET /admin/stats만.

import type { AdminSnapshot } from '../types/domain';
import { apiGet } from './client';

/** GET /admin/stats. term 생략(또는 '전체')이면 전역, 아니면 해당 학기. */
export function getStats(term?: string): Promise<AdminSnapshot> {
  const qs = term && term !== '전체' ? `?${new URLSearchParams({ term }).toString()}` : '';
  return apiGet<AdminSnapshot>(`/admin/stats${qs}`);
}
