from datetime import datetime
from typing import Any
from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlmodel import Field, SQLModel
from pgvector.sqlalchemy import Vector
from sourcealignrec.core.config import settings


class User(SQLModel, table=True):
    """프론트 인증 사용자. api-contract/auth.md §4 User 스키마 정합."""
    id: str = Field(primary_key=True)                          # server-generated (UUID)
    email: str = Field(unique=True, index=True)
    password_hash: str
    school: str
    department: str
    grade: int                                                 # 1~6 (초과학기 포함)
    admission_year: int                                        # YYYY
    name: str | None = None
    role: str = Field(default="student")                       # student | admin (admin = operator)
    grad_total_required: int | None = None                     # 졸업 총 이수학점(영역 최소합과 별개 스칼라). 미설정=None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WishlistItem(SQLModel, table=True):
    """본인 위시리스트. (user_id, offering_id) UNIQUE. api-contract/wishlist.md 정합.
    정렬 키는 created_at — 우선순위·드래그 reorder UI 미도입 (디자인 정본 부재)."""
    __tablename__ = "wishlist_item"
    __table_args__ = (
        UniqueConstraint("user_id", "offering_id", name="uq_wishlist_user_offering"),
    )
    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    offering_id: str = Field(foreign_key="offering.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Timetable(SQLModel, table=True):
    """시간표 시안. user당 최소 1개 보장 — signup transaction에서 빈 "시안 1" 자동 생성.
    api-contract/timetable.md 정합. courses는 별도 TimetableCourse row."""
    id: str = Field(primary_key=True)                          # server-generated (UUID hex)
    user_id: str = Field(foreign_key="user.id", index=True)
    name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TimetableCourse(SQLModel, table=True):
    """시간표에 등록된 강의. (timetable_id, offering_id) UNIQUE.
    course 순서는 의미 없음 — ScheduleGrid가 요일/시간으로 배치."""
    __tablename__ = "timetable_course"
    __table_args__ = (
        UniqueConstraint("timetable_id", "offering_id", name="uq_timetable_course_tt_offering"),
    )
    id: int | None = Field(default=None, primary_key=True)
    timetable_id: str = Field(foreign_key="timetable.id", index=True)
    offering_id: str = Field(foreign_key="offering.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CourseHistory(SQLModel, table=True):
    """본인 수강이력 entry. api-contract/history.md 정합.
    course_id: 카탈로그 매칭 시 실제 Course.id (FK), 직접입력(custom)이면 None.
      → 추천 Hard Filter taken_course_ids는 is_custom=False & course_id IS NOT NULL인 row만 사용.
    중복(같은 course_id·term) 제약 미부여 — prototype 단순화, 사용자가 add/remove로 관리."""
    __tablename__ = "course_history"
    id: str = Field(primary_key=True)                          # server-generated (UUID hex)
    user_id: str = Field(foreign_key="user.id", index=True)
    course_id: str | None = Field(default=None, foreign_key="course.id", index=True)
    course_name: str
    credits: int
    course_type: str                                           # 이수구분 (전공필수/전공선택/전공기초/교양)
    term: str                                                  # YYYY-N
    grade: str                                                 # letter당 +/0/- (A+·A0·A-…), F, P
    is_custom: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class GraduationRequirement(SQLModel, table=True):
    """본인 졸업요건 카테고리·학점. (user_id, category) UNIQUE — PUT upsert 기준.
    default 시드 없음(학과/입학년도마다 달라 보편 default 부재) — 신규 유저는 빈 list."""
    __tablename__ = "graduation_requirement"
    __table_args__ = (
        UniqueConstraint("user_id", "category", name="uq_grad_req_user_category"),
    )
    id: str = Field(primary_key=True)                          # server-generated (UUID hex)
    user_id: str = Field(foreign_key="user.id", index=True)
    category: str                                              # free-form (이수구분명 또는 사용자 추가)
    required: int


class Course(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str


class Professor(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    affiliation: str | None = None  # 소속 (소프트웨어융합대학 컴퓨터공학부 등)


class Department(SQLModel, table=True):
    """학과 레지스트리. KHU 포털 메타데이터(major rows)에서 시드.
    User.department(자유문자열) → code resolve 및 per-학과 이수구분(OfferingDeptClassification)의 학과 키 출처."""
    code: str = Field(primary_key=True)           # 포털 p_major 코드 (예: A10627)
    name: str                                     # full path (소프트웨어융합대학 컴퓨터공학부 컴퓨터공학과)
    college_name: str | None = None
    english_name: str | None = None


class Offering(SQLModel, table=True):
    """특정 학기의 과목 개설 단위."""
    id: str = Field(primary_key=True)
    course_id: str = Field(foreign_key="course.id", index=True)
    professor_id: str = Field(foreign_key="professor.id", index=True)
    term: str
    # 기본 정보 스칼라
    credits: int | None = None           # 학점
    course_type: str | None = None       # 이수구분 (전공필수/전공선택/교양 등)
    dept_name: str | None = None         # 개설학과
    is_english: bool = False             # 영어(부분)강좌 여부
    is_online: bool = False              # 온라인(비대면) 강의 여부 — time_place에 "온라인" 포함 시 True
    notice: str | None = None            # 수강신청 시스템 원본 특이사항 (학사 메타, 자유 텍스트)
    meetings_json: str = Field(default="[]")  # [{day, start_time, end_time, room}] (api-contract/_common.md §4 Weekday)
    recognized_depts_json: str = Field(default="[]")  # [{code, name}] — 이 강의를 학점 인정해주는 학과 list
    syllabus_url: str | None = None      # 학교 강의계획서 원문 permalink (공개, loginYn=N)
    # 레거시 flattened text (임베딩·검색용)
    syllabus_text: str | None = None
    # 구조화 필드 (JSON)
    course_overview: str | None = None
    learning_objectives: str | None = None
    instruction_type_note: str | None = None
    instruction_type_ratios: str = Field(default="[]")  # [{type, ratio_pct}]
    evaluation_items: str = Field(default="[]")          # [{item, ratio, note}]
    weekly_topics: str = Field(default="[]")             # [str, ...]
    prerequisite_courses: str = Field(default="[]")      # [{name, required}]


class OfferingDeptClassification(SQLModel, table=True):
    """per-(offering, 조회학과) 이수구분. KHU 카탈로그 field_gb에서 추출.

    이수구분은 과목 고정 속성이 아니라 조회학과별로 다르다 (예: 고급딥러닝 인공지능학과=전공필수,
    컴퓨터공학과=전공선택). dept_code가 등장 = 그 학과 카탈로그에 인정됨. Offering.course_type(개설학과
    단일값)은 학생 기준 아님 — 본 테이블이 학생 렌즈의 정본."""
    __tablename__ = "offering_dept_classification"
    __table_args__ = (
        UniqueConstraint("offering_id", "dept_code", name="uq_offering_dept_classification_offering_dept"),
    )
    id: int | None = Field(default=None, primary_key=True)
    offering_id: str = Field(foreign_key="offering.id", index=True)
    dept_code: str = Field(foreign_key="department.code", index=True)
    dept_name: str
    course_type: str   # 이수구분 (전공필수/전공선택/전공기초/일반선택/...)


class Review(SQLModel, table=True):
    """원본 강의평. 분류 결과의 정본은 ReviewClassification(is_noise) 테이블이다.

    source: 'crawled'(오프라인 sar-ingest 적재) | 'user'(프론트에서 사용자 직접 등록).
    author_id: 'user' 리뷰의 작성자(로그인 사용자). 'crawled'는 null.
    created_at: 'user' 리뷰의 제출 시각. 'crawled'는 원 작성일 불명이라 null.
    """
    id: str = Field(primary_key=True)
    course_id: str = Field(foreign_key="course.id", index=True)
    professor_id: str = Field(foreign_key="professor.id", index=True)
    term: str  # 리뷰 대상 강의의 개설학기(semester_text 파싱). 크롤링/등록 시점 아님.
    raw_text: str
    source: str = Field(default="crawled")  # crawled | user
    author_id: str | None = Field(default=None, foreign_key="user.id", index=True)
    created_at: datetime | None = Field(default=None)
    # DEPRECATED dead field — 파이프라인이 채우지 않음(항상 'unprocessed'). 분류는
    # ReviewClassification 테이블에서 파생(is_noise). 신규 코드는 참조 금지. 컬럼은
    # 하위호환 위해 유지(drop 미정).
    classification: str = Field(default="unprocessed")
    embedding: Any = Field(
        default=None,
        sa_column=Column(Vector(settings.embedding_dim)),
    )


class OfferingAttribute(SQLModel, table=True):
    """Hard Filter에 쓰이는 과목 속성.
    review 소스는 Course+Professor 전 학기 리뷰 집계, syllabus 소스는 해당 Offering 기준."""
    __tablename__ = "offering_attribute"
    id: int | None = Field(default=None, primary_key=True)
    offering_id: str = Field(foreign_key="offering.id", index=True)
    attribute_name: str   # grading_leniency | assignment_load | team_project | exam_weight
    attribute_value: str  # 너그러움/보통/깐깐함 | 많음/보통/적음 | 높음/보통/낮음
    source: str           # review | syllabus


class ReviewClassification(SQLModel, table=True):
    """BERT ReviewClassifier 추론 결과. 타입별 p-score와 noise 여부 저장."""
    __tablename__ = "review_classification"
    id: int | None = Field(default=None, primary_key=True)
    review_id: str = Field(foreign_key="review.id", index=True)
    grading_score: float = 0.0
    exam_score: float = 0.0
    assignment_score: float = 0.0
    attendance_score: float = 0.0
    teaching_score: float = 0.0
    topic_score: float = 0.0
    professor_score: float = 0.0
    is_noise: bool = False
    model_path: str = ""
    classified_at: datetime = Field(default_factory=datetime.utcnow)


class RepresentativeReview(SQLModel, table=True):
    """DynamicScore 알고리즘으로 선정한 대표 리뷰. Course+Professor 단위."""
    __tablename__ = "representative_review"
    id: int | None = Field(default=None, primary_key=True)
    course_id: str = Field(foreign_key="course.id", index=True)
    professor_id: str = Field(foreign_key="professor.id", index=True)
    review_id: str = Field(foreign_key="review.id")
    rank: int = 1
    classifier_model_path: str = ""
    selected_at: datetime = Field(default_factory=datetime.utcnow)


class ProfessorRepresentativeReview(SQLModel, table=True):
    """교수 단위 대표 리뷰. professor/teaching/grading/assignment/attendance 타입 리뷰만 선정."""
    __tablename__ = "professor_representative_review"
    id: int | None = Field(default=None, primary_key=True)
    professor_id: str = Field(foreign_key="professor.id", index=True)
    review_id: str = Field(foreign_key="review.id")
    rank: int = 1
    classifier_model_path: str = ""
    selected_at: datetime = Field(default_factory=datetime.utcnow)


class OfferingProfile(SQLModel, table=True):
    """강의계획서 + 대표 리뷰 LLM 요약. 유사도 검색의 기준이자 LLM 추천 컨텍스트.

    profile_json: LLM이 생성한 5필드 구조(topic/format/evaluation/reviews_summary/caveats)의 JSON 문자열. UI 렌더링·LLM 컨텍스트·임베딩의 source of truth.
    profile_text: profile_json + 메타(과목명·교수명·학기) 헤더로 조립한 자연어 텍스트. 임베딩과 LLM 컨텍스트에 사용.
    review_count: profile 산출에 사용된 전체 리뷰 수 (UI 메타 표시용, nullable: 미산출 시).
    profile_updated_at: profile 마지막 생성/갱신 시각 (UI '갱신일' 표시용).
    """
    __tablename__ = "offering_profile"
    offering_id: str = Field(primary_key=True, foreign_key="offering.id")
    profile_json: str | None = None
    profile_text: str
    review_count: int | None = None
    profile_updated_at: datetime | None = None
    embedding: Any = Field(
        default=None,
        sa_column=Column(Vector(settings.embedding_dim)),
    )


class ProfessorProfile(SQLModel, table=True):
    """교수 단위 4필드 프로필. 교수 페이지 UI 표시 전용 (검색·추천 미사용).

    OfferingProfile과 schema 의미는 다르다(과목 단위가 아닌 교수 단위 집계). 과목 주제(topic)는
    의도적으로 제외 — 교수 페이지의 강의 목록 섹션이 담당(build_professor_profiles.py 참조).
    - format: 강의 운영 방식 경향
    - evaluation: 평가 경향
    - reviews_summary: 학생 평 종합
    - caveats: 유의사항

    profile_json: LLM이 생성한 4필드 구조의 JSON 문자열. UI 렌더링 source of truth.
    source_review_count: profile 산출에 사용된 ProfessorRepresentativeReview 수 (provenance).
    profile_updated_at: profile 마지막 생성/갱신 시각.
    """
    __tablename__ = "professor_profile"
    professor_id: str = Field(primary_key=True, foreign_key="professor.id")
    profile_json: str | None = None
    source_review_count: int = 0
    profile_updated_at: datetime | None = None


class OfferingSearchEmbedding(SQLModel, table=True):
    """벤치마크 ablation용 검색 변종 임베딩. (offering_id, variant) 단위로 한 row.

    variant:
    - 'syllabus'           : System A 검색용. 강의계획서 텍스트 임베딩.
    - 'syllabus_repreview' : System B 검색용. 강의계획서 + 대표 리뷰 raw concat 임베딩.
    """
    __tablename__ = "offering_search_embedding"
    __table_args__ = (UniqueConstraint("offering_id", "variant", name="uq_search_embedding_offering_variant"),)
    id: int | None = Field(default=None, primary_key=True)
    offering_id: str = Field(foreign_key="offering.id", index=True)
    variant: str
    embedding: Any = Field(
        default=None,
        sa_column=Column(Vector(settings.embedding_dim)),
    )


# ── ReviewTypeLabel (ReviewClassifier 학습 데이터) ────────────────────────────

class ReviewTypeLabel(SQLModel, table=True):
    """리뷰 타입 multi-label (gold). LLM 라벨링 → 인간 검수 흐름으로 관리.

    source='llm'  : LLM이 생성한 초안
    source='human': 검수 완료본 (학습 시 우선 사용)
    """
    __tablename__ = "review_type_label"
    id: int | None = Field(default=None, primary_key=True)
    review_id: str = Field(foreign_key="review.id", index=True)
    grading: bool = False
    exam: bool = False
    assignment: bool = False
    attendance: bool = False
    teaching: bool = False
    topic: bool = False
    professor: bool = False
    is_noise: bool = False      # 어떤 타입에도 해당 안 됨
    source: str = "llm"         # llm | human
    labeler: str | None = None  # model_id 또는 검수자 이름
    split: str | None = None    # train | eval (None=미지정)


class ReviewAttribute(SQLModel, table=True):
    """per-review Attribute 추출 결과. LLM 또는 BERT extractor 출력을 저장."""
    __tablename__ = "review_attribute"
    id: int | None = Field(default=None, primary_key=True)
    review_id: str = Field(foreign_key="review.id", index=True)
    attribute_name: str   # grading_leniency | assignment_load | team_project | attendance_strictness
    attribute_value: str  # 너그러움/보통/깐깐함 | 많음/보통/적음 | ...
    extractor: str        # llm:<model_id> | bert:<model_path>
    extracted_at: datetime = Field(default_factory=datetime.utcnow)


class ReviewAttributeExtraction(SQLModel, table=True):
    """AttributeExtraction 처리 마커. 후보 리뷰를 extractor가 처리했음을 기록(결과 0건이어도).

    '처리했으나 추출 결과 없음'과 '미처리'를 구분하기 위함 — ReviewAttribute row 유무로는
    둘을 구별 못 함. extractor가 처리한 모든 후보에 1행. admin 미처리 집계의 정본.
    """
    __tablename__ = "review_attribute_extraction"
    review_id: str = Field(primary_key=True, foreign_key="review.id")
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    extractor: str | None = None


class ReviewAttributeLabel(SQLModel, table=True):
    """BERT AttributeExtractor 학습용 고품질 라벨. Claude 또는 사람이 직접 라벨링.

    없음 = 해당 리뷰에 그 속성 신호 없음 (class 0).
    """
    __tablename__ = "review_attribute_label"
    id: int | None = Field(default=None, primary_key=True)
    review_id: str = Field(foreign_key="review.id", index=True, unique=True)
    grading_leniency: str = "없음"       # 없음 | 너그러움 | 보통 | 깐깐함
    assignment_load: str = "없음"         # 없음 | 많음 | 보통 | 적음
    team_project: str = "없음"            # 없음 | 있음
    attendance_strictness: str = "없음"   # 없음 | 엄격함 | 보통 | 너그러움
    labeler: str = "claude-sonnet-4-6"
    labeled_at: datetime = Field(default_factory=datetime.utcnow)
    split: str | None = Field(default=None)  # train | eval (None=미지정)


# ── Benchmark ─────────────────────────────────────────────────────────────────

class BenchmarkCase(SQLModel, table=True):
    """Gold label이 있는 benchmark 케이스."""
    __tablename__ = "benchmark_case"
    case_id: str = Field(primary_key=True)
    target: str                           # review_decomp | ...
    review_id: str | None = Field(default=None, foreign_key="review.id", index=True)
    review_text: str | None = None        # review_id 없을 때 직접 입력
    gold_classification: str              # valid | noise
    gold_attrs: str = Field(default="[]") # JSON: [{name, value}, ...]
    coverage_tag: str = ""
    memo: str | None = None


class BenchmarkRun(SQLModel, table=True):
    """한 번의 benchmark 실행 단위."""
    __tablename__ = "benchmark_run"
    run_id: int | None = Field(default=None, primary_key=True)
    target: str
    model_id: str
    impl_variant: str = "llm_zero_shot"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    notes: str | None = None


class BenchmarkResult(SQLModel, table=True):
    """케이스별 실행 결과."""
    __tablename__ = "benchmark_result"
    result_id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="benchmark_run.run_id", index=True)
    case_id: str = Field(foreign_key="benchmark_case.case_id")
    pred_classification: str
    pred_attrs: str = Field(default="[]")  # JSON
    clf_correct: bool
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0


# ── E2E Benchmark ─────────────────────────────────────────────────────────────
# 컴포넌트 벤치마크(BenchmarkCase/Run/Result)와 별도. E2E 시나리오는 yaml에서 직접
# 로드하고 실행 결과만 DB에 저장. 설계: backend/work/e2e-benchmark/runner-design.md.

class E2EBenchmarkRun(SQLModel, table=True):
    """E2E 벤치마크 실행 1회 단위 메타. user-supplied run_id."""
    __tablename__ = "e2e_benchmark_run"
    run_id: str = Field(primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    recommend_model: str                                # model-pool model_id
    scenario_file_hash: str                             # yaml 파일 SHA256
    schema_prompt_hash: str                             # _common.BASE_SYSTEM_PROMPT SHA256
    settings_json: str = Field(default="{}")            # K, shortlist_size, embedding_model, temperature 등
    notes: str | None = None


class E2EExecution(SQLModel, table=True):
    """E2E 벤치마크 row — (run, scenario, system) 단위 한 번의 시스템 실행."""
    __tablename__ = "e2e_execution"
    __table_args__ = (
        UniqueConstraint("run_id", "scenario_id", "system_variant",
                         name="uq_e2e_execution_run_scenario_system"),
    )

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="e2e_benchmark_run.run_id", index=True)
    scenario_id: str = Field(index=True)
    scenario_snapshot_json: str                         # 시나리오 전체 JSON 스냅샷
    type: str | None = None                             # initial만 (topic_focused/preference_focused/mixed)
    case_role: str                                      # initial_recommendation/follow_up_grounding/follow_up_preference_shift
    system_variant: str                                 # A | B | C | D
    status: str                                         # success/parse_error/invalid_offering_id/tpm_exceeded/call_error/skipped
    schema_honored: bool = False
    retry_count: int = 0
    transcript_json: str = Field(default="[]")          # LLM 호출 전체 transcript
    recommendations_json: str | None = None             # 파싱된 RecommendationOutput JSON (recommend case 한정)
    explanation: str | None = None                      # ConversationOutput.explanation (grounding case)
    tool_calls_json: str | None = None                  # D converse tool 시퀀스 (list[str])
    shortlist_ids_json: str | None = None               # 검색 단계 shortlist offering_id 목록 (list[str])
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    duration_ms: int = 0
    error_message: str | None = None
    # sanity 메트릭 (per-row 계산, SQL on-the-fly 집계)
    attribute_violation: bool = False
    must_not_violation: bool = False
    positive_coverage_count: int = 0
    positive_set_size: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RetrievalExecution(SQLModel, table=True):
    """Retrieval phase row — LLM 호출 없는 결정적 단계.

    (run_id, scenario_id, system_variant) 단위 한 row. shortlist + offering별 context를 저장해
    generation runner가 동일 입력으로 LLM call만 다시 돌릴 수 있게 함.

    grounding 시나리오는 본 테이블에 들어가지 않음 (retrieval/generation 분리 불가, 별도 grounding runner).
    """
    __tablename__ = "retrieval_execution"
    __table_args__ = (
        UniqueConstraint("run_id", "scenario_id", "system_variant",
                         name="uq_retrieval_execution_run_scenario_system"),
    )

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="e2e_benchmark_run.run_id", index=True)
    scenario_id: str = Field(index=True)
    scenario_snapshot_json: str                         # 시나리오 전체 JSON 스냅샷 (generation·judge 재사용)
    type: str | None = None                             # topic_focused/preference_focused/mixed
    system_variant: str                                 # A | B | C | D | CD
    status: str                                         # success | retrieval_error | skipped
    shortlist_ids_json: str = Field(default="[]")       # list[str], pgvector 검색 순서 보존
    context_per_offering_json: str = Field(default="{}")  # dict[offering_id, str]
    query_embedding: Any = Field(                       # 분석/재현용 (redundant — 같은 시나리오 row들이 동일 값)
        default=None,
        sa_column=Column(Vector(settings.embedding_dim)),
    )
    duration_ms: int = 0
    error_message: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class GenerationExecution(SQLModel, table=True):
    """Generation phase row — RetrievalExecution을 LLM input으로 재조립 후 호출 결과.

    같은 RetrievalExecution에 generation을 여러 번 시도하면 안 되도록 UNIQUE — 모델·temperature 변경
    실험은 새 run_id로 retrieval부터 재실행하는 게 의도. (편의를 위해 풀면 sanity 메트릭 해석이 모호해짐.)
    """
    __tablename__ = "generation_execution"
    __table_args__ = (
        UniqueConstraint("retrieval_execution_id",
                         name="uq_generation_execution_retrieval"),
    )

    id: int | None = Field(default=None, primary_key=True)
    retrieval_execution_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("retrieval_execution.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        ),
    )
    status: str                                         # success | parse_error | invalid_offering_id | tpm_exceeded | call_error
    schema_honored: bool = False
    retry_count: int = 0
    transcript_json: str = Field(default="[]")
    recommendations_json: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    duration_ms: int = 0
    error_message: str | None = None
    # sanity 메트릭 (recommendation 단계 — grounding은 별도)
    attribute_violation: bool = False
    positive_coverage_count: int = 0
    positive_set_size: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BenchmarkJudgment(SQLModel, table=True):
    """LLM-as-judge 점수 — (execution, item, dimension) 단위.
    설계: docs/03-implementation/llm-judge.md §7.

    execution_id (e2e_execution FK)는 11주차 데이터 호환용으로 유지. 새 채점은
    generation_execution_id 사용. 정확히 한 컬럼만 채워져야 함 (application-level 검증).
    """
    __tablename__ = "benchmark_judgment"
    id: int | None = Field(default=None, primary_key=True)
    execution_id: int | None = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("e2e_execution.id", ondelete="CASCADE"),
            index=True,
            nullable=True,
        ),
    )
    generation_execution_id: int | None = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("generation_execution.id", ondelete="CASCADE"),
            index=True,
            nullable=True,
        ),
    )
    dimension: str                                      # relevance | faithfulness | specificity
    item_offering_id: str | None = None                 # per-item 차원이 아니면 NULL (e.g., follow_up Relevance overall)
    score: int | None = None                            # 1-5. success row만 작성되므로 사실상 non-null.
    rationale: str | None = None
    status: str = "success"                             # success만 기록 (judge_runner는 비-success 시 row 미작성하고 fail-fast).
    judge_model: str                                    # claude code subagent 사용 모델 alias (sonnet)
    judge_model_id: str | None = None                   # 응답 metadata의 정확 model id
    judge_agent_name: str                               # benchmark-judge-{dim}
    judge_prompt_hash: str                              # agent 파일 SHA256
    created_at: datetime = Field(default_factory=datetime.utcnow)
