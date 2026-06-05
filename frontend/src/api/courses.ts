// api-contract/courses.md 정합. mock 분기 미도입 — 카탈로그 picker는 backend 연결 필수.
// 수강이력 "검색·추가" 전용. 추천용 의미검색(api/search.ts)과 별개.

import { apiGet } from './client';

/** GET /courses 결과 1건. credits/courseType/department는 대표 Offering 출처(없으면 0/""/null). */
export interface CourseHit {
  id: string;
  name: string;
  credits: number;
  courseType: string;
  department: string | null;
}

interface CourseSearchResponse {
  items: CourseHit[];
}

export function search(q: string, limit = 20): Promise<CourseSearchResponse> {
  const params = new URLSearchParams({ q, limit: String(limit) });
  return apiGet<CourseSearchResponse>(`/courses?${params.toString()}`);
}
