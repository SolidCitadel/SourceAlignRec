import type { OfferingSearchResult } from '../../types/domain';
import { fixtureSearchResults } from '../../fixtures/searchResults';
import {
  mockRecommend as fixtureMockRecommend,
  mockExplain,
} from '../../fixtures/mockRecommend';
import { ApiError } from '../client';
import type {
  RecommendConverseRequest,
  RecommendInitialRequest,
  RecommendResponse,
} from '../recommend';

function lookupCandidates(ids: string[]): OfferingSearchResult[] {
  const byId = new Map(fixtureSearchResults.map((r) => [r.id, r]));
  return ids
    .map((id) => byId.get(id))
    .filter((r): r is OfferingSearchResult => r !== undefined);
}

export async function mockRecommend(req: RecommendInitialRequest): Promise<RecommendResponse> {
  if (!req.candidateOfferingIds.length) {
    throw new ApiError(400, '추천할 후보 강의가 없습니다.');
  }
  const shortlist = lookupCandidates(req.candidateOfferingIds);
  const recommendations = fixtureMockRecommend(shortlist, req.query);
  return {
    status: 'success',
    messages: [
      { role: 'user', content: req.query },
      { role: 'assistant', content: `${recommendations.length}개 추천 생성` },
    ],
    recommendations,
    explanation: null,
  };
}

export async function mockConverse(req: RecommendConverseRequest): Promise<RecommendResponse> {
  if (!req.messages.length) {
    throw new ApiError(400, 'converse 모드에는 messages가 필요합니다.');
  }
  const explanation = mockExplain(
    req.messages.map((m) => ({ text: m.content })),
    req.query,
  );
  return {
    status: 'success',
    messages: [...req.messages, { role: 'assistant', content: explanation }],
    recommendations: null,
    explanation,
  };
}
