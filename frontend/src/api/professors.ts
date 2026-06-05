// api-contract/professors.md 정합. mock 분기 미도입 — fixture 폐기, backend 연결 필수.

import type { ProfessorDetail } from '../types/domain';
import { apiGet } from './client';

export function get(id: string): Promise<ProfessorDetail> {
  return apiGet<ProfessorDetail>(`/professors/${encodeURIComponent(id)}`);
}
