import type { ClassMeeting, Weekday } from '../types/domain';

const DAY_LABEL: Record<Weekday, string> = {
  Mon: '월',
  Tue: '화',
  Wed: '수',
  Thu: '목',
  Fri: '금',
};

/** "소프트웨어융합대학 컴퓨터공학부 컴퓨터공학과" → "컴퓨터공학과".
 *  카드·필터 같은 short-form 표시에만 사용. 상세에서는 풀패스 유지. */
export function lastDeptSegment(dept: string): string {
  if (!dept) return dept;
  const segments = dept.trim().split(/\s+/);
  return segments[segments.length - 1];
}

/** offeringId(`CSE33002_2026-1`) → 학수번호-분반(`CSE330-02`).
 *  종합정보시스템 강의 목록의 "학수번호-분반" 칼럼 표기와 일치. 끝 2자가 분반. */
export function formatCourseCode(offeringId: string): string {
  const sylcode = offeringId.split('_')[0];
  if (sylcode.length < 3) return sylcode;
  return `${sylcode.slice(0, -2)}-${sylcode.slice(-2)}`;
}

/** 같은 시간대 묶음: '월·수 11:00~12:15' / 여러 시간대면 ' / '로 구분. */
export function formatMeetings(meetings: ClassMeeting[]): string {
  const groups = new Map<string, Weekday[]>();
  const order: string[] = [];
  for (const m of meetings) {
    const key = `${m.startTime}~${m.endTime}`;
    if (!groups.has(key)) {
      groups.set(key, []);
      order.push(key);
    }
    groups.get(key)!.push(m.day);
  }
  return order
    .map((key) => {
      const days = groups.get(key)!.map((d) => DAY_LABEL[d]).join('·');
      return `${days} ${key}`;
    })
    .join(' / ');
}
