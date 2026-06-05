import type { OfferingSearchResult, SearchFilter, SortKey } from '../../types/domain';
import { fixtureSearchResults } from '../../fixtures/searchResults';
import type { SearchRequest, SearchResponse } from '../search';

const UNKNOWN_CHIP = '정보 없음';

/** chip 선택값과 attribute 값 매칭. null 값은 '정보 없음' chip이 있을 때만 통과. */
function attrMatches(selected: string[], value: string | null): boolean {
  if (selected.length === 0) return true;  // 미적용
  if (value === null) return selected.includes(UNKNOWN_CHIP);
  return selected.includes(value);
}

function matchesFilter(r: OfferingSearchResult, f: SearchFilter): boolean {
  // 학과 단일선택 = 이수구분 렌즈 — mock은 렌즈 데이터가 없어 학과 필터 미적용(dev stub).
  if (f.courseTypes.length && !f.courseTypes.includes(r.type)) return false;
  if (f.credits.length && !f.credits.includes(r.credit)) return false;
  if (f.englishOnly && !r.englishOnly) return false;
  if (f.keyword.trim()) {
    const k = f.keyword.trim().toLowerCase();
    if (
      !r.courseName.toLowerCase().includes(k) &&
      !r.professorName.toLowerCase().includes(k)
    )
      return false;
  }
  const a = f.attributes;
  if (!attrMatches(a.grading, r.attributes.grading)) return false;
  if (!attrMatches(a.assignment, r.attributes.assignment)) return false;
  if (!attrMatches(a.teamProject, r.attributes.teamProject)) return false;
  if (!attrMatches(a.examWeight, r.attributes.examWeight)) return false;
  if (!attrMatches(a.attendance, r.attributes.attendance)) return false;
  return true;
}

function sortResults(results: OfferingSearchResult[], sort: SortKey): OfferingSearchResult[] {
  const sorted = [...results];
  switch (sort) {
    case 'course_name':
      sorted.sort((a, b) => a.courseName.localeCompare(b.courseName, 'ko'));
      break;
    case 'course_id':
      sorted.sort((a, b) => a.id.localeCompare(b.id));
      break;
    case 'credit':
      sorted.sort((a, b) => b.credit - a.credit);
      break;
  }
  return sorted;
}

export async function mockSearch(req: SearchRequest): Promise<SearchResponse> {
  const filtered = fixtureSearchResults.filter((r) => matchesFilter(r, req.filter));
  const sorted = sortResults(filtered, req.sort);
  return { results: sorted.slice(0, 100) };
}
