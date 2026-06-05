import type { RecommendationCard } from '../types/domain';
import { apiPost, USE_MOCK } from './client';
import { mockRecommend, mockConverse } from './mock/recommend';

export interface ChatTurn {
  role: 'user' | 'assistant';
  content: string;
}

export type RecommendStatus = 'success' | 'parse_error' | 'invalid_offering_id';

export interface RecommendResponse {
  status: RecommendStatus;
  messages: ChatTurn[];
  recommendations: RecommendationCard[] | null;
  explanation: string | null;
}

export interface RecommendInitialRequest {
  mode: 'initial';
  query: string;
  candidateOfferingIds: string[];
  messages: [];
}

export interface RecommendConverseRequest {
  mode: 'converse';
  query: string;
  // 직전 추천된 과목 id(rank 순). 후속 질문의 grounding·tool 조회 범위. 길이 1 이상.
  recommendedOfferingIds: string[];
  messages: ChatTurn[];
}

export type RecommendRequest = RecommendInitialRequest | RecommendConverseRequest;

export function recommend(req: RecommendRequest): Promise<RecommendResponse> {
  if (USE_MOCK) return req.mode === 'initial' ? mockRecommend(req) : mockConverse(req);
  return apiPost<RecommendResponse>('/recommend', req);
}
