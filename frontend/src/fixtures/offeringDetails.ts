import type {
  EvaluationItem,
  LateralOffering,
  OfferingDetail,
  OfferingSearchResult,
  RepresentativeReview,
  WeeklyTopic,
} from '../types/domain';
import { fixtureSearchResults } from './searchResults';

const CURRENT_TERM = '2026-2';

function evaluationFor(r: OfferingSearchResult): EvaluationItem[] {
  // attribute 기반 가중치 — 시험·과제 비중 변형
  const examHeavy = r.attributes.examWeight === '높음';
  const examLight = r.attributes.examWeight === '낮음';
  const assignmentHeavy = r.attributes.assignment === '많음';
  if (examHeavy) {
    return [
      { item: '중간고사', weight: 30 },
      { item: '기말고사', weight: 40 },
      { item: '과제', weight: 20 },
      { item: '출석', weight: 10 },
    ];
  }
  if (examLight && assignmentHeavy) {
    return [
      { item: '중간고사', weight: 15 },
      { item: '기말고사', weight: 15 },
      { item: '과제', weight: 50 },
      { item: '팀 프로젝트', weight: 15 },
      { item: '출석', weight: 5 },
    ];
  }
  return [
    { item: '중간고사', weight: 25 },
    { item: '기말고사', weight: 25 },
    { item: '과제', weight: 30 },
    { item: '발표', weight: 10 },
    { item: '출석', weight: 10 },
  ];
}

function weeklyTopicsFor(r: OfferingSearchResult): WeeklyTopic[] {
  const courseName = r.courseName;
  return [
    { week: 1, topic: `오리엔테이션 + ${courseName} 개요` },
    { week: 2, topic: '기본 개념과 용어 정리' },
    { week: 3, topic: '핵심 원리 도입' },
    { week: 4, topic: '기초 응용 1' },
    { week: 5, topic: '기초 응용 2' },
    { week: 6, topic: '중간 복습' },
    { week: 7, topic: '중간고사' },
    { week: 8, topic: '심화 주제 1' },
    { week: 9, topic: '심화 주제 2' },
    { week: 10, topic: '사례 분석' },
    { week: 11, topic: '응용 프로젝트' },
    { week: 12, topic: '응용 프로젝트 진행' },
    { week: 13, topic: '발표 및 토론' },
    { week: 14, topic: '복습' },
    { week: 15, topic: '기말고사' },
  ];
}

function prerequisitesFor(r: OfferingSearchResult): string[] {
  // course id 패턴 기반 mock
  if (r.id === 'oop' || r.id === 'ds') return ['프로그래밍 기초'];
  if (r.id === 'algo') return ['자료구조'];
  if (r.id === 'comp') return ['자료구조', '운영체제'];
  if (r.id === 'ml' || r.id === 'dm') return ['확률과통계', '선형대수학'];
  if (r.id === 'ai') return ['머신러닝 입문'];
  if (r.id === 'regression' || r.id === 'bayes') return ['확률과통계'];
  return [];
}

function representativeReviewsFor(r: OfferingSearchResult): RepresentativeReview[] {
  const prof = r.professorName;
  const a = r.attributes;
  return [
    {
      id: `${r.id}-rr1`,
      rank: 1,
      types: ['grading', 'exam'],
      term: '2026-1',
      text: `채점은 ${a.grading}한 편. ${a.examWeight === '높음' ? '시험 출제 패턴을 파악하는 게 학점 관건' : '꾸준한 과제 수행이 더 중요'}. 학기 후반에 부담이 몰리니 일정 관리 필요.`,
    },
    {
      id: `${r.id}-rr2`,
      rank: 2,
      types: ['professor', 'assignment'],
      term: '2025-2',
      text: `${prof} 교수님은 설명이 명확하고 질문을 환영. 다만 ${a.assignment === '많음' ? '과제 양이 많아 시간 투자가 필요' : '과제 양은 무난한 편'}.`,
    },
    {
      id: `${r.id}-rr3`,
      rank: 3,
      types: a.teamProject === '있음' ? ['topic', 'assignment'] : ['topic'],
      term: '2025-2',
      text: `${r.courseName}는 ${r.type === '전공필수' ? '전공 기초로 반드시 다지고 가야 할 내용' : '관심 있다면 흥미롭게 들을 수 있는 내용'}. ${a.teamProject === '있음' ? '팀 프로젝트가 비중이 커서 팀원 운이 중요' : ''}`,
    },
    {
      id: `${r.id}-rr4`,
      rank: 4,
      types: ['topic', 'exam'],
      term: '2025-1',
      text: `사전 학습으로 ${prerequisitesFor(r)[0] ?? '관련 기초 과목'}을 들었다면 따라가기 수월. ${a.examWeight === '높음' ? '족보보다는 강의 노트 정리가 훨씬 효과적' : '평소 강의 출석 + 노트만 잘 정리해도 충분'}.`,
    },
    {
      id: `${r.id}-rr5`,
      rank: 5,
      types: a.grading === '깐깐함' ? ['grading'] : ['grading', 'attendance'],
      term: '2025-1',
      text: `${a.grading === '깐깐함' ? '점수 변별이 확실해서 노력한 만큼 결과가 나옴' : '전반적으로 너그러워서 출석·과제만 충실히 해도 무난'}.`,
    },
  ];
}

const SAME_COURSE_STUB: Record<string, LateralOffering[]> = {
  oop: [
    { id: 'oop-2025-2', term: '2025-2', professorName: '이대호' },
    { id: 'oop-2025-1', term: '2025-1', professorName: '김교수' },
    { id: 'oop-2024-2', term: '2024-2', professorName: '이대호' },
  ],
  ds: [
    { id: 'ds-2025-2', term: '2025-2', professorName: '박교수' },
    { id: 'ds-2025-1', term: '2025-1', professorName: '한교수' },
  ],
  algo: [
    { id: 'algo-2025-2', term: '2025-2', professorName: '한교수' },
  ],
};

function sameProfessorFor(r: OfferingSearchResult): LateralOffering[] {
  // 동일 교수가 가르치는 다른 과목 stub
  if (r.professorName === '이교수') {
    return [
      { id: 'philo', term: '2026-2', professorName: '이교수', courseName: '윤리학 입문' },
      { id: 'writing', term: '2026-2', professorName: '이교수', courseName: '글쓰기' },
    ];
  }
  if (r.professorName === '윤교수') {
    return [
      { id: 'db', term: '2026-2', professorName: '윤교수', courseName: '데이터베이스' },
      { id: 'design-thinking', term: '2026-2', professorName: '윤교수', courseName: '디자인 씽킹' },
    ];
  }
  if (r.professorName === '박교수') {
    return [
      { id: 'ds', term: '2026-2', professorName: '박교수', courseName: '자료구조' },
      { id: 'stat', term: '2026-2', professorName: '박교수', courseName: '확률과통계' },
    ];
  }
  return [];
}

// 결정적 mock 메타 — id 해시 기반. 실제 백엔드 연동 전엔 안정적인 값이면 충분.
function mockReviewCount(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return 18 + (h % 80); // 18 ~ 97
}

// 수강신청 시스템 원본 특이사항 mock. 학교 시스템에 어떤 식으로 적혀 있는지 가능한 톤 살림.
const NOTICE_STUB: Record<string, string> = {
  oop: '본인 노트북으로 실습 (필요시 학과 사무실 대여 가능).\n첫 주 환경 설정 OT 필수 참석.',
  ds: '실습실 PC 사용. 매주 실습 코드 LMS 제출.',
  algo: '선수과목 미수강 시 사전 면담 필요. 매주 백준 과제 제출.',
  comp: '강의 30%·실습 70%. 노트북 지참.',
  ml: '원어 강의(영어). Python·NumPy 기초 사전 학습 권장.',
  ai: '원어 강의(영어). 팀 프로젝트 2회 진행.',
  dm: '데이터 분석 도구(pandas) 사전 학습 권장.',
  regression: '통계학 1·2 또는 동등 과목 선이수 권장.',
  bayes: 'R 또는 Python 통계 패키지 사용. 노트북 지참.',
  writing: '매주 글쓰기 과제 제출. 합평 세션 참여 의무.',
  philo: '독서량 다소 많음(주당 약 30p).',
  econ: '계산기 지참(공학용 가능).',
  history: '서술형 시험 위주. 노트 직접 필기 권장.',
};

function buildDetail(r: OfferingSearchResult): OfferingDetail {
  const a = r.attributes;
  return {
    ...r,
    professorId: r.professorName,   // mock: 이름을 id 대용 (mock 모드 전용 placeholder)
    reviewCount: mockReviewCount(r.id),
    profileUpdatedAt: '2026-05-09',
    notice: NOTICE_STUB[r.id] ?? null,
    syllabusUrl: `https://sugang.khu.ac.kr/core?attribute=lectPlan&p_code=${r.id}&loginYn=N`,
    profile: {
      topic: `${r.courseName}는 ${r.department} ${r.type} 과목으로, ${r.id.includes('intro') ? '기초 개념과' : '핵심 주제'}를 다룹니다.`,
      format: `${a.teamProject === '있음' ? '팀 프로젝트' : '개인 과제'} 중심 + 강의식. ${r.englishOnly ? '영어 강좌.' : ''}`,
      evaluation: `${a.examWeight === '높음' ? '시험 비중이 큰 편' : a.examWeight === '낮음' ? '시험보다 과제·발표 비중' : '시험·과제 균형 잡힌 비중'}. 채점은 ${a.grading} 편.`,
      reviewsSummary: `학생들은 ${a.assignment === '많음' ? '과제 부담을 큰 약점으로' : '학습량이 적당하다는 점을 강점으로'} 꼽음. ${r.professorName} 교수님은 ${a.grading === '너그러움' ? '점수 인심이 좋고' : '평가가 엄격하지만 공정'}하다는 평.`,
      caveats: `${a.examWeight === '높음' ? '시험 기간 학습량이 집중되어 부담 가능.' : ''}${a.teamProject === '있음' ? ' 팀원 선정과 일정 관리가 학점에 영향.' : ''}${prerequisitesFor(r).length > 0 ? ` 사전에 ${prerequisitesFor(r).join(', ')} 학습 권장.` : ''}`.trim() || '특별한 주의사항 없음.',
    },
    evaluation: evaluationFor(r),
    weeklyTopics: weeklyTopicsFor(r),
    prerequisites: prerequisitesFor(r),
    representativeReviews: representativeReviewsFor(r),
    lateral: {
      sameCourse: SAME_COURSE_STUB[r.id] ?? [],
      sameProfessor: sameProfessorFor(r),
    },
  };
}

/** id로 OfferingDetail lookup. 없으면 null. */
export function getOfferingDetail(id: string | null): OfferingDetail | null {
  if (!id) return null;
  const r = fixtureSearchResults.find((s) => s.id === id);
  if (!r) return null;
  return buildDetail(r);
}

export { CURRENT_TERM };
