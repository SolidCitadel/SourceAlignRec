import type { OfferingDetail } from '../types/domain';
import { apiGet, USE_MOCK } from './client';
import { mockGetOffering } from './mock/offerings';

export function getOffering(id: string): Promise<OfferingDetail> {
  if (USE_MOCK) return mockGetOffering(id);
  return apiGet<OfferingDetail>(`/offerings/${encodeURIComponent(id)}`);
}
