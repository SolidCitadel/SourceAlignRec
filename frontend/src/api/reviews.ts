// api-contract/reviews.md 정합. mock 분기 미도입 — fixture 폐기, backend 연결 필수.

import type { ReviewItem } from '../types/domain';
import { apiGet, apiPost } from './client';

interface ReviewListResponse {
  items: ReviewItem[];
}

export function list(offeringId: string): Promise<ReviewListResponse> {
  return apiGet<ReviewListResponse>(`/offerings/${encodeURIComponent(offeringId)}/reviews`);
}

export interface ReviewCreateBody {
  term: string;
  text: string;
}

/** 사용자 직접 강의평 등록. 등록 리뷰 1건(status='unprocessed') 반환. */
export function create(offeringId: string, body: ReviewCreateBody): Promise<ReviewItem> {
  return apiPost<ReviewItem>(`/offerings/${encodeURIComponent(offeringId)}/reviews`, body);
}
