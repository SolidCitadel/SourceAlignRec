// 도메인 타입 — 화면 포팅 진행하면서 surface가 요구하는 모양에 따라 점진적으로 확장.
// 이 파일이 백엔드 API 계약의 초안 역할.

// 이수구분 type은 자유 문자열. 두 축이 섞이지 않게 enum union을 두지 않는다:
//  - 검색·추천·offering의 type = KHU 이수구분(학생 본인 학과 렌즈, 동적 라벨 — '교양' 같은 고정값 아님).
//    학과 정책별로 동일 강의도 다른 값(예: 컴공=전공필수, 인공지능=전공선택).
//  - history.courseType = 졸업요건 영역(RequirementCategory와 같은 축). 별개 개념.

export interface OfferingSummary {
  id: string;
  courseName: string;
  professorName: string;
  credit: number;
  type: string;
}

export type Weekday = 'Mon' | 'Tue' | 'Wed' | 'Thu' | 'Fri';

export interface ClassMeeting {
  day: Weekday;
  /** 24h "HH:MM" */
  startTime: string;
  endTime: string;
  room?: string;
}

/** Wishlist에 담긴 offering. 배치에 필요한 meetings 포함. */
export interface WishlistItem extends OfferingSummary {
  meetings: ClassMeeting[];
}

/** UI에서 사용할 derived view — 활성 timetable과 시간 양립 토글로부터 계산. */
export interface WishlistItemView extends WishlistItem {
  /** 활성 timetable과 시간 충돌 (시간 양립 ON일 때만 true 가능) */
  conflict: boolean;
  /** 활성 timetable에 이미 같은 offering이 있음 */
  inSchedule: boolean;
}

export interface ScheduledCourse extends OfferingSummary {
  meetings: ClassMeeting[];
  /** 온라인(비대면) 강의. meetings 비어 그리드 배치 불가 → 하단 영역에 표시. */
  isOnline: boolean;
}

export interface Timetable {
  id: string;
  name: string;
  courses: ScheduledCourse[];
}

export type WorkspaceMode = '시간표 짜기' | '과목 찾기';

// === 과목 찾기 (검색·필터) ===

export type GradingLeniency = '너그러움' | '보통' | '깐깐함';
export type AssignmentLoad = '많음' | '보통' | '적음';
export type TeamProject = '있음' | '없음';
export type ExamWeight = '높음' | '보통' | '낮음';
export type AttendanceStrictness = '엄격함' | '보통' | '너그러움';

/** filter chip enum: 위 값들 + '정보 없음' (응답이 null인 강의 통과). */
export type AttributeFilterValue = string;
export const UNKNOWN = '정보 없음' as const;

/** chip 값 enum. "보통"은 강의평 기반 카테고리에선 winner 거의 안 나오고 의미 모호하므로 제거.
 *  examWeight는 강의계획서 정량 기반(시험 비중 임계값)이라 "보통" 유지 + 모든 강의 채워짐 = null 강의 없음 → 정보 없음 chip 불필요. */
export const ATTR_VALUES = {
  grading: ['너그러움', '깐깐함', UNKNOWN] as const,
  assignment: ['많음', '적음', UNKNOWN] as const,
  teamProject: ['있음', '없음', UNKNOWN] as const,
  examWeight: ['높음', '보통', '낮음'] as const,
  attendance: ['엄격함', '너그러움', UNKNOWN] as const,
} as const;

/** 카테고리별 라벨 + hover hint. UI에서 일관 사용. */
export const ATTR_META: Record<
  'grading' | 'assignment' | 'teamProject' | 'examWeight' | 'attendance',
  { label: string; hint: string }
> = {
  grading: {
    label: '채점',
    hint: '강의평 기반 채점이 너그러운지/깐깐한지 의견 통계입니다.',
  },
  assignment: {
    label: '과제',
    hint: '강의평 기반 과제 양 의견 통계입니다.',
  },
  teamProject: {
    label: '팀플',
    hint: '강의평 기반 팀 프로젝트 유무입니다.',
  },
  examWeight: {
    label: '시험 비중',
    hint: '강의계획서 기반 시험 평가 비중입니다.',
  },
  attendance: {
    label: '출결',
    hint: '강의평 기반 출결 엄격함 의견 통계입니다.',
  },
};

/** examWeight chip별 추가 hint (임계값). 다른 카테고리 chip엔 hint 없음. */
export const EXAM_WEIGHT_CHIP_HINT: Record<string, string> = {
  '높음': '시험 ≥60%입니다',
  '보통': '시험 30~60%입니다',
  '낮음': '시험 <30%입니다',
};

/** 응답 OfferingAttribute: row 없거나 winner '없음'이면 null. UI는 칩 미표시. */
export interface OfferingAttributes {
  grading: GradingLeniency | null;
  assignment: AssignmentLoad | null;
  teamProject: TeamProject | null;
  examWeight: ExamWeight | null;
  attendance: AttendanceStrictness | null;
}

export interface OfferingSearchResult extends OfferingSummary {
  department: string;
  englishOnly: boolean;
  /** 온라인(비대면) 강의. time_place에 "온라인" 명시된 경우. */
  isOnline: boolean;
  meetings: ClassMeeting[];
  attributes: OfferingAttributes;
  /** 본인 수강이력에 있는 과목(course 매칭). '수료 숨김' 토글 대상. (api-contract/search.md §3) */
  taken: boolean;
  /** taken=true일 때 최신 학기 성적, 아니면 null. "이미 수강 · {성적}" 표기용. */
  takenGrade: string | null;
}

export interface SearchFilter {
  /** 단일 학과 code (예: 'A10627') = 카탈로그 필터 + 이수구분 렌즈. '' = 본인 학과 자동 (백엔드 resolve). */
  department: string;
  /** KHU 이수구분 라벨(선택 학과 카탈로그 실재값, /departments가 제공). 빈 배열 = 전체.
   *  졸업요건 영역(RequirementCategory)과 다른 축 — history와 공유하지 않는다. */
  courseTypes: string[];
  credits: number[];
  keyword: string;
  englishOnly: boolean;
  /** 각 카테고리 chip 값들. 빈 배열 = 미적용. '정보 없음' 포함 시 응답 null 강의 통과. */
  attributes: {
    grading: string[];
    assignment: string[];
    teamProject: string[];
    examWeight: string[];
    attendance: string[];
  };
}

export type SortKey = 'course_name' | 'course_id' | 'credit';

/** UI derived view — 활성 timetable과의 충돌/등록 여부 포함. */
export interface OfferingSearchResultView extends OfferingSearchResult {
  conflict: boolean;
  inSchedule: boolean;
  inWishlist: boolean;
}

// === AI 추천 ===

export interface RecommendationCard {
  rank: number;
  offeringId: string;
  courseName: string;
  professorName: string;
  credit: number;
  type: string;
  department: string;
  meetings: ClassMeeting[];
  rationale: string;
}

export type ChatMessage =
  | { id: string; role: 'user'; text: string }
  | { id: string; role: 'assistant'; kind: 'recommend'; recommendations: RecommendationCard[] }
  | { id: string; role: 'assistant'; kind: 'explanation'; text: string }
  | { id: string; role: 'assistant'; kind: 'notice'; text: string };

// === Offering 상세 ===

// 백엔드 OfferingProfile.profile_json (LLM 산출 5필드)와 1:1 매핑.
// snake_case ↔ camelCase: reviews_summary ↔ reviewsSummary. 그 외는 동일.
// 필드 구성은 백엔드 schema가 결정 — 프론트가 임의 추가·제거 X.
export interface OfferingProfile5 {
  topic: string;
  format: string;
  evaluation: string;
  reviewsSummary: string;
  caveats: string;
}

export interface EvaluationItem {
  /** 중간고사 / 기말고사 / 과제 / 출석 / 발표 / 기타 */
  item: string;
  /** 0-100, 합 100 가정 */
  weight: number;
  note?: string;
}

export interface WeeklyTopic {
  week: number;
  topic: string;
}

// 백엔드 ReviewClassifier 7타입과 1:1 매핑 (architecture.md "리뷰 분류" 섹션).
// AI/모델 산출물이라 프론트가 임의 추가·제거·재명명 X.
export type ReviewClassificationType =
  | 'grading'
  | 'exam'
  | 'assignment'
  | 'attendance'
  | 'teaching'
  | 'topic'
  | 'professor';

export const REVIEW_TYPE_LABEL: Record<ReviewClassificationType, string> = {
  grading: '채점',
  exam: '시험',
  assignment: '과제',
  attendance: '출결',
  teaching: '강의',
  topic: '주제',
  professor: '교수',
};

export const REVIEW_TYPE_ORDER: ReviewClassificationType[] = [
  'grading',
  'exam',
  'assignment',
  'attendance',
  'teaching',
  'topic',
  'professor',
];

/** 리뷰 분류 상태. noise 제외, valid + unprocessed 노출 (spec L940). */
export type ReviewClassificationStatus = 'valid' | 'unprocessed' | 'noise';

export interface RepresentativeReview {
  id: string;
  rank: number;
  text: string;
  /** 분류기 multi-label. UI는 REVIEW_TYPE_LABEL로 한글 표기. */
  types: ReviewClassificationType[];
  term?: string;
}

/** 전체 리뷰 페이지(`/offering/:id/reviews`)용 raw 리뷰. spec L832-840. */
export interface ReviewItem {
  id: string;
  text: string;
  term: string;
  /** 'noise'는 응답에서 제외되지만 타입 안전 위해 포함. */
  status: ReviewClassificationStatus;
  types: ReviewClassificationType[];
}

// === Professor 페이지 ===

/**
 * 교수 종합 프로필 — 교수 일반화 가능한 4필드.
 * 과목 주제(topic)는 의도적으로 제외 — 그 교수가 무엇을 가르치는지는 강의 목록 섹션이 담당하고,
 * 프로필은 "어떤 교수인지"(운영·평가·소통·유의사항)에 집중한다.
 * - format: 강의 운영 방식 경향
 * - evaluation: 평가 경향
 * - reviewsSummary: 학생 평 종합
 * - caveats: 유의사항
 */
export interface ProfessorProfile {
  format: string;
  evaluation: string;
  reviewsSummary: string;
  caveats: string;
}

export interface ProfessorRepresentativeReview {
  id: string;
  rank: number;
  text: string;
  term: string;
  types: ReviewClassificationType[];
}

export interface ProfessorOfferingSummary {
  id: string;
  courseName: string;
  term: string;
  type: string;
}

export interface ProfessorDetail {
  id: string;
  name: string;
  /** 소속 단일 문자열 (원본 affiliation이 college/department로 분리 안 됨). 없으면 null. */
  affiliation: string | null;
  reviewCount: number;
  /** 교수 종합 5필드 프로필. 미생성 시 null (별도 subplan) → UI는 placeholder. */
  profile: ProfessorProfile | null;
  representativeReviews: ProfessorRepresentativeReview[];
  offerings: ProfessorOfferingSummary[];
}

// === Admin 대시보드 ===

export interface AdminCounts {
  /** 수집학과 수 — 크롤링한 학과 카탈로그 범위(인정학과 distinct). */
  departments: number;
  course: number;
  offering: number;
  review: number;
}

export interface AdminReviewClassificationCounts {
  unprocessed: number;
  valid: number;
  noise: number;
}

export interface AdminPipelineStep {
  name: string;
  input: number;
  processed: number;
  pending: number;
  lastRunAt: string;
  /** false면 학기 무관(전 학기 집계) 단계 — 학기 선택해도 카운트가 전체로 유지됨. */
  termScoped: boolean;
}

export interface AdminLogEntry {
  timestamp: string;
  task: string;
  duration: string;
  status: 'ok' | 'fail';
}

export interface AdminSnapshot {
  counts: AdminCounts;
  classification: AdminReviewClassificationCounts;
  pipeline: AdminPipelineStep[];
  /** 실행 로그 — 현재 항상 빈 list(읽기 전용). 실행 트리거 도입 시 채워짐. */
  recentLogs: AdminLogEntry[];
  /** 학기 selector 옵션 (백엔드 distinct Offering.term desc). '전체'는 프론트에서 prepend. */
  availableTerms: string[];
}

export interface LateralOffering {
  id: string;
  term: string;
  professorName: string;
  /** 다른 과목인 경우 (이 교수 다른 과목) */
  courseName?: string;
}

// === 사용자 (인증·온보딩) ===

export interface User {
  id: string;
  email: string;
  school: string;
  /** 학과 — 카탈로그 매칭 또는 자유 입력 */
  department: string;
  /** 1~6 (초과학기 포함) */
  grade: number;
  /** YYYY */
  admissionYear: number;
  /** 표시 이름. 신규 가입은 필수지만 name 도입 전 기존 계정은 null → UI는 fallback(이메일 local-part). */
  name: string | null;
  /** 가입 default 'student'. admin만 /admin 접근 — 승격은 백엔드 CLI(sar-grant-admin) */
  role: 'student' | 'admin';
}

export interface SignupForm {
  email: string;
  password: string;
  school: string;
  department: string;
  grade: number;
  admissionYear: number;
  name: string;
}

// === 수강 이력 + 졸업 진행률 ===

/** 학점 grade. 본교는 letter당 +/0/- 3단위(A+·A0·A-…). F는 낙제, P는 Pass(이수처리). */
export type Grade =
  | 'A+' | 'A0' | 'A-'
  | 'B+' | 'B0' | 'B-'
  | 'C+' | 'C0' | 'C-'
  | 'D+' | 'D0' | 'D-'
  | 'F' | 'P';

/**
 * 수강 이력 entry. spec L562: `(course_id, term)` 단위.
 * courseId: 카탈로그(`GET /courses`)에서 고른 실제 Course.id. 직접 입력(custom)이면 null.
 * custom=true: 사용자가 직접 입력한 시스템 외 과목 (courseId=null).
 *   Hard filter 영향 없음(courseId 없으므로 "이미 수강" 제외 대상 아님), 졸업 진행률 합산에만 포함.
 */
export interface HistoryEntry {
  id: string;
  courseId: string | null;
  courseName: string;
  credits: number;
  /** 졸업요건 영역(RequirementCategory와 같은 축). KHU 이수구분이 아니라 학생 본인의 졸업요건 버킷. */
  courseType: RequirementCategory;
  term: string;
  grade: Grade;
  custom?: boolean;
}

/**
 * 졸업요건 카테고리. 학과/입학년도마다 다양하므로 free-form string. 사용자가 추가/삭제 가능.
 * 졸업요건 설정이 정본 — history.courseType은 이 카테고리 목록에서 선택하므로 항상 일치, 전부 자동 합산.
 */
export type RequirementCategory = string;

export interface GraduationRequirement {
  category: RequirementCategory;
  required: number;
}

/**
 * UI 노출용 derived view.
 * 졸업요건은 두 축으로 독립: ① 졸업 총 이수학점(gradTotalRequired) ② 영역별 최소(byCategory).
 * 헤드라인 진행률은 ①(totalCredits / gradTotalRequired) 기준 — 영역 최소의 합이 아님.
 * 영역별 최소의 합이 총 이수학점보다 작은 게 정상(차액 = 자유학점).
 */
export interface GraduationProgress {
  /** F 제외 이수 학점 합. */
  totalCredits: number;
  /** 졸업 총 이수학점(사용자 설정). 미설정 시 null — 헤드라인은 "총학점 미설정" 안내로 대체. */
  gradTotalRequired: number | null;
  /** 영역별 최소 충족 현황. 모든 카테고리가 history.courseType과 같은 축이라 current 자동 합산. */
  byCategory: {
    category: RequirementCategory;
    current: number;
    required: number;
  }[];
}

export interface OfferingDetail extends OfferingSearchResult {
  /** 교수 페이지(`/professor/:id`) 링크용 (api-contract professors.md §2). */
  professorId: string;
  profile: OfferingProfile5;
  /** profile 생성 시점 (YYYY-MM-DD) */
  profileUpdatedAt: string;
  /** profile/요약 산출에 사용된 전체 리뷰 수 */
  reviewCount: number;
  /** 수강신청 시스템 원본 특이사항 (학사 메타). 자유 텍스트, 줄바꿈 가능. 없으면 null. */
  notice: string | null;
  /** 학교 강의계획서 원문 permalink (공개). 미수집이면 null → 버튼 숨김. */
  syllabusUrl: string | null;
  evaluation: EvaluationItem[];
  weeklyTopics: WeeklyTopic[];
  prerequisites: string[];
  representativeReviews: RepresentativeReview[];
  lateral: {
    sameCourse: LateralOffering[];
    sameProfessor: LateralOffering[];
  };
}


