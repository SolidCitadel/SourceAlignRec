import type {
  OfferingSearchResult,
  RecommendationCard,
} from '../types/domain';

function rationaleFor(r: OfferingSearchResult, query: string): string {
  const a = r.attributes;
  const q = query.trim() ? `"${query.trim()}"` : '조건';
  return `${q}에 대해 ${r.courseName} 추천. 채점 ${a.grading} · 과제 ${a.assignment} · 팀플 ${a.teamProject} · 시험 ${a.examWeight} 조합.`;
}

/**
 * 검색 결과 shortlist 안에서 K=3 추천.
 * 백엔드 미구현 — 결정적 mock (상위 N개 reverse picking).
 */
export function mockRecommend(
  shortlist: OfferingSearchResult[],
  query: string,
): RecommendationCard[] {
  const k = Math.min(3, shortlist.length);
  // 쿼리 길이를 시드로 약간의 변화 — 같은 풀이라도 다른 query에 다른 순서.
  const seed = query.length;
  const picks: OfferingSearchResult[] = [];
  for (let i = 0; i < k; i++) {
    const idx = (i * 3 + seed) % shortlist.length;
    if (!picks.includes(shortlist[idx])) picks.push(shortlist[idx]);
  }
  // 부족하면 앞에서 보강
  for (const r of shortlist) {
    if (picks.length >= k) break;
    if (!picks.includes(r)) picks.push(r);
  }
  return picks.map((r, i) => ({
    rank: i + 1,
    offeringId: r.id,
    courseName: r.courseName,
    professorName: r.professorName,
    credit: r.credit,
    type: r.type,
    department: r.department,
    meetings: r.meetings,
    rationale: rationaleFor(r, query),
  }));
}

const EXPLANATION_TEMPLATES = [
  '카드 1번이 가장 부합하는 이유는 채점·과제 부담이 사용자가 언급한 조건에 비교적 적합하기 때문입니다.',
  '세 카드 모두 같은 학과 풀에서 뽑혔지만, 시험 비중·팀플 비중에서 차이가 있어 분산했습니다.',
  '제시한 조건 외에 학기 진행 부담을 함께 고려한 추천입니다. 더 좁히고 싶다면 attribute 필터를 조정해보세요.',
];

export function mockExplain(_messages: { text: string }[], query: string): string {
  const idx = (query.length * 7) % EXPLANATION_TEMPLATES.length;
  return EXPLANATION_TEMPLATES[idx];
}
