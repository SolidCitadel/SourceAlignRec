import type { OfferingSearchResult, SearchFilter, SortKey } from '../types/domain';
import { apiGet, apiPost, USE_MOCK } from './client';
import { mockSearch } from './mock/search';

export interface DepartmentOption {
  code: string;
  name: string;
  /** 그 학과 카탈로그 실재 이수구분 라벨(위계순). 이수구분 필터 선택지 — 하드코딩 아님. */
  courseTypes: string[];
}

/** 검색 학과 단일선택 선택지 (이수구분 데이터 있는 학과). */
export function fetchDepartments(): Promise<DepartmentOption[]> {
  if (USE_MOCK) return Promise.resolve([]);
  return apiGet<DepartmentOption[]>('/departments');
}

export interface SearchRequest {
  filter: SearchFilter;
  sort: SortKey;
}

export interface SearchResponse {
  results: OfferingSearchResult[];
}

export function search(input: SearchRequest): Promise<SearchResponse> {
  if (USE_MOCK) return mockSearch(input);
  return apiPost<SearchResponse>('/search', input);
}
