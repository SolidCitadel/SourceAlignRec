// api-contract/history.md §1-3 정합. mock 분기 미도입 — backend 연결 필수.

import type { HistoryEntry } from '../types/domain';
import { apiDelete, apiGet, apiPost } from './client';

interface HistoryListResponse {
  items: HistoryEntry[];
}

interface HistoryItemResponse {
  item: HistoryEntry;
}

export function list(): Promise<HistoryListResponse> {
  return apiGet<HistoryListResponse>('/history');
}

export function add(entry: Omit<HistoryEntry, 'id'>): Promise<HistoryItemResponse> {
  return apiPost<HistoryItemResponse>('/history', entry);
}

export function remove(id: string): Promise<void> {
  return apiDelete<void>(`/history/${encodeURIComponent(id)}`);
}
