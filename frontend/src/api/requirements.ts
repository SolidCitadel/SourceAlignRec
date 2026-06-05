// api-contract/history.md §4-6 정합. mock 분기 미도입 — backend 연결 필수.

import type { GraduationRequirement } from '../types/domain';
import { apiDelete, apiGet, apiPut } from './client';

interface RequirementsResponse {
  /** 졸업 총 이수학점(per-user 스칼라). 미설정 시 null. 영역합과 별개. */
  totalRequired: number | null;
  items: GraduationRequirement[];
}

interface RequirementItemResponse {
  item: GraduationRequirement;
}

interface TotalResponse {
  totalRequired: number;
}

export function list(): Promise<RequirementsResponse> {
  return apiGet<RequirementsResponse>('/requirements');
}

/** 졸업 총 이수학점 설정 (카테고리와 무관한 스칼라 upsert). */
export function setTotal(required: number): Promise<TotalResponse> {
  return apiPut<TotalResponse>('/requirements/total', { required });
}

/** (category) 단위 upsert — 추가 + 학점 수정 겸용. */
export function upsert(category: string, required: number): Promise<RequirementItemResponse> {
  return apiPut<RequirementItemResponse>(
    `/requirements/${encodeURIComponent(category)}`,
    { required },
  );
}

export function remove(category: string): Promise<void> {
  return apiDelete<void>(`/requirements/${encodeURIComponent(category)}`);
}
