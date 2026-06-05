import type { OfferingDetail } from '../../types/domain';
import { getOfferingDetail } from '../../fixtures/offeringDetails';
import { ApiError } from '../client';

export async function mockGetOffering(id: string): Promise<OfferingDetail> {
  const detail = getOfferingDetail(id);
  if (!detail) throw new ApiError(404, '강의를 찾을 수 없습니다.');
  return detail;
}
