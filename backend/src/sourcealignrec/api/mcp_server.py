"""FastMCP 서버 — online.mcp 도구 5개를 MCP로 노출.

ChatKHU(LLM)가 대화 중 호출하는 도구. 인증 없음(공개) — ChatKHU엔 user 개념이 없다.
각 tool은 Session을 열어 online.mcp 도메인 함수에 위임한다(도구는 stateless, 세션은 호출마다).

mount는 api/main.py에서 `mcp.http_app(transport=...)`로 streamable HTTP + SSE 둘 다 노출.

※ description·파라미터 설명의 독자는 **도구를 호출하는 LLM**이다(학생은 LLM의 답변만 본다).
   목표 = LLM이 도구 용도·인자·반환을 정확히 이해하고 학생의 자연어를 올바른 호출로 옮기는 것.
   - enum은 스키마(Literal)로 강제하고, **각 값의 의미를 설명**한다(값만 나열 금지).
   - DynamicScore·OfferingProfile 같은 내부 구현 용어는 description에 넣지 않는다(LLM에 무의미).
   - 반환 필드명(found/note/reason/rationale 등)은 LLM이 받는 실제 키이므로 설명한다.
"""
from __future__ import annotations

from typing import Annotated, Literal

from fastmcp import FastMCP
from pydantic import Field
from sqlmodel import Session

from sourcealignrec.db.session import engine
from sourcealignrec.online import mcp as tools

mcp = FastMCP("SourceAlignRec")

# ── 강의 특성 필터 (search/recommend 공통) — 값 의미를 LLM에 설명 ─────────────────
# taxonomy 정본: docs/03-implementation/architecture.md §Attribute. 값은 DB 저장값과 일치.
Grading = Literal["너그러움", "깐깐함"]
Assignment = Literal["많음", "적음"]
TeamProject = Literal["있음", "없음"]
ExamWeight = Literal["높음", "보통", "낮음"]
Attendance = Literal["엄격함", "너그러움"]

# 카탈로그(이수구분 분류)가 수집된 학과 — 정본: dept_lens.available_departments. 추가 수집 시 갱신.
# 이 셋만 department로 받는다(나머지는 카탈로그가 없어 학과 한정·이수구분이 무의미).
Dept = Literal["컴퓨터공학과", "인공지능학과", "소프트웨어융합학과"]
# 위 세 학과 카탈로그의 실제 이수구분(전부 동일). 정본: dept_lens.dept_course_types.
CourseType = Literal["전공기초", "전공필수", "전공선택"]

_F_GRADING = "학점을 주는 경향. '너그러움'=학점을 후하게 줌, '깐깐함'=학점을 짜게 줌."
_F_ASSIGNMENT = "과제 양. '많음'=과제 부담이 큼, '적음'=과제가 적음."
_F_TEAM = "팀 프로젝트 유무. '있음'=팀플이 있는 강의, '없음'=팀플이 없는 강의."
_F_EXAM = "성적에서 시험이 차지하는 비중. '높음'/'보통'/'낮음'."
_F_ATTEND = "출결 관리 엄격함. '엄격함'=출석을 깐깐히 봄, '너그러움'=느슨함."
_F_DEPT = (
    "강의를 그 학과 카탈로그로 한정하고 이수구분(type)을 그 학과 기준으로 매긴다(같은 과목도 학과마다 "
    "이수구분이 다름). 카탈로그가 수집된 학과는 이 셋뿐이다 — 다른 학과 강의는 department를 비우고 "
    "검색하라(학과 무관 검색, 이수구분은 안 매겨짐)."
)
_F_TYPES = "이수구분으로 거르기. department를 함께 지정해야 적용된다."
_F_CREDITS = "학점으로 거르기 (예: [3])."
_F_ENGLISH = "영어로 진행하는 강의만 볼지 여부."

# ── 강의평 타입 (get_reviews_all 필터) — 분류기 7타입, 값 의미를 LLM에 설명 ─────────
# taxonomy 정본: docs/03-implementation/architecture.md §ReviewClassifier. 값은 분류기 출력과 일치.
ReviewType = Literal[
    "grading", "exam", "assignment", "attendance", "teaching", "topic", "professor"
]
_F_REVIEW_TYPES = (
    "강의평을 다루는 측면으로 좁히기(선택). 지정한 타입 중 하나라도 다룬 강의평만 남는다. "
    "값: grading(학점·성적 분포), exam(시험·퀴즈 방식/난이도/족보), assignment(과제·팀플·프로젝트 양), "
    "attendance(출결 관리), teaching(강의력·설명·전달), topic(다루는 주제·내용), "
    "professor(교수 성향·태도·소통). 미지정이면 전체 강의평을 최신순으로 준다 — 특정 측면이 궁금할 때만 좁혀라."
)
_F_REVIEW_LIMIT = "한 번에 받을 강의평 수 (기본 30, 최대 50)."
_F_REVIEW_OFFSET = "건너뛸 개수 (페이지네이션). 다음 페이지는 직전 offset+limit으로 호출."

# 강의 특성 필터의 동작을 LLM이 알도록 — 공통 주의문.
_FILTER_NOTE = (
    "강의 특성(grading·assignment·team_project·exam_weight·attendance)으로 거르면 그 특성이 "
    "파악된 강의만 남고 정보가 없는 강의는 제외된다. 너무 좁아지면 특성 필터를 빼고 검색한 뒤 "
    "get_course로 후보의 프로필·강의평을 직접 확인하라."
)

# search/recommend description은 _FILTER_NOTE를 합쳐야 해서 데코레이터 description= 인자로 전달한다.
# (도크스트링에 `"...".format(...)`를 쓰면 문자열 표현식이라 __doc__로 인식되지 않아 설명이 누락된다.)
_SEARCH_DESC = (
    "키워드와 조건으로 개설 강의 목록을 찾는다. 각 결과에는 offering_id가 있어 "
    "get_course·get_syllabus·get_reviews_all·recommend_courses에 그대로 쓴다. 조건에 맞는 강의가 없으면 "
    "results는 빈 배열이고 note에 사유가 담긴다. department를 지정했는데 그 학과 카탈로그가 아직 "
    "수집되지 않았으면 빈 results와 함께 note가 '미수집'임을 알리고 가능한 학과를 안내한다 — 이 경우 "
    "'과목이 없다'고 답하지 말고 note의 학과를 쓰라.\n" + _FILTER_NOTE
)
_RECOMMEND_DESC = (
    "후보 강의들(offering_ids) 중에서 학생의 자연어 요구에 가장 맞는 소수를 골라 추천 이유(rationale)와 함께 "
    "돌려준다. 후보를 일일이 읽고 비교하는 대신 강의평·강의계획서 기반으로 적합도를 매겨 랭킹해 준다. "
    "offering_ids는 후보 모집단으로, 보통 search_courses 결과의 offering_id들을 넘긴다(필터링은 search가, "
    "랭킹은 이 도구가 담당). 추천은 현재 컴퓨터공학과 강의만 지원한다 — search_courses에 "
    "department='컴퓨터공학과'로 찾은 후보를 넘겨라(다른 학과 후보는 no_profiled_candidates가 된다). "
    "학생이 조건에 맞는 과목을 골라 달라거나 무엇을 들을지 의견을 구할 때 쓸 만하다. "
    "recommendations가 비면 reason으로 사유를 구분한다: no_candidates(offering_ids가 비어 있음), "
    "no_profiled_candidates(후보 중 추천에 쓸 분석 정보가 준비된 과목 없음), "
    "generation_failed(생성 실패). note에 사람이 읽을 사유가 담긴다."
)


def _attrs(grading, assignment, team_project, exam_weight, attendance):
    out = {
        "grading": grading,
        "assignment": assignment,
        "team_project": team_project,
        "exam_weight": exam_weight,
        "attendance": attendance,
    }
    return {k: v for k, v in out.items() if v}


@mcp.tool(description=_SEARCH_DESC)
def search_courses(
    query: Annotated[str, Field(description="과목명 또는 교수명의 부분 문자열로 매칭할 키워드.")] = "",
    department: Annotated[Dept | None, Field(description=_F_DEPT)] = None,
    course_types: Annotated[list[CourseType] | None, Field(description=_F_TYPES)] = None,
    credits: Annotated[list[int] | None, Field(description=_F_CREDITS)] = None,
    grading: Annotated[list[Grading] | None, Field(description=_F_GRADING)] = None,
    assignment: Annotated[list[Assignment] | None, Field(description=_F_ASSIGNMENT)] = None,
    team_project: Annotated[list[TeamProject] | None, Field(description=_F_TEAM)] = None,
    exam_weight: Annotated[list[ExamWeight] | None, Field(description=_F_EXAM)] = None,
    attendance: Annotated[list[Attendance] | None, Field(description=_F_ATTEND)] = None,
    english_only: Annotated[bool, Field(description=_F_ENGLISH)] = False,
    limit: Annotated[int, Field(description="돌려줄 강의 개수 상한.")] = 50,
) -> dict:
    """키워드·조건 강의 검색 (설명은 _SEARCH_DESC)."""
    with Session(engine) as s:
        return tools.search_courses(
            s, query,
            department=department, course_types=course_types, credits=credits,
            attributes=_attrs(grading, assignment, team_project, exam_weight, attendance),
            english_only=english_only, limit=limit,
        )


@mcp.tool
def get_course(
    offering_id: Annotated[str, Field(description="강의 ID. 검색·추천 결과에 들어 있는 값.")],
) -> dict:
    """강의 한 개의 상세 — 메타 + 종합 프로필 + 대표 강의평을 한 번에 반환한다.

    학점·이수구분·시간표·강의 특성에 더해, profile(강의 운영·평가 경향과 학생 평을 종합한 5개 항목:
    topic·format·evaluation·reviews_summary·caveats)과 reviews(대표 강의평 원문)를 담는다. 강의의
    전반적 성격·분위기·평가 경향을 묻는 질문은 이 한 번의 호출로 충분하다. 주차별 주제·평가 비중 같은
    강의계획서의 축자 사실이 필요하면 get_syllabus, 특정 측면의 더 많은 강의평이 필요하면
    get_reviews_all을 추가로 쓴다. found=false면 그 id의 강의가 없는 것. 종합 프로필이 없으면
    profile=null + profile_note, 강의평이 없으면 reviews=[] + reviews_note — 없는 내용을 지어내지 말 것."""
    with Session(engine) as s:
        return tools.get_course(s, offering_id)


@mcp.tool
def get_syllabus(
    offering_id: Annotated[str, Field(description="강의 ID. 검색·추천 결과에 들어 있는 값.")],
) -> dict:
    """강의계획서 원문(축자 사실)을 반환한다.

    수업 개요·학습목표·주차별 주제·평가 항목(비중)·선수과목 등 강의계획서에 명시된 구체 사실이
    필요할 때 호출한다(예: "평가 비중 어떻게 돼?", "몇 주차에 뭐 배워?", "선수과목 있어?"). 강의의
    종합 성격·분위기는 get_course의 profile로 충분하다. found=false면 강의 자체가 없음.
    syllabus=null이면 강의계획서가 비어 있는 것 — 없는 내용을 지어내지 말 것."""
    with Session(engine) as s:
        return tools.get_syllabus(s, offering_id)


@mcp.tool
def get_reviews_all(
    offering_id: Annotated[str, Field(description="강의 ID. 검색·추천 결과에 들어 있는 값.")],
    types: Annotated[list[ReviewType] | None, Field(description=_F_REVIEW_TYPES)] = None,
    limit: Annotated[int, Field(description=_F_REVIEW_LIMIT)] = 30,
    offset: Annotated[int, Field(description=_F_REVIEW_OFFSET)] = 0,
) -> dict:
    """그 강의의 강의평 원문을 더 많이(대표 강의평 너머) 조회한다.

    get_course가 주는 대표 강의평으로 부족하거나, 특정 측면(시험·과제 등)의 강의평을 더 보고 싶을 때
    호출한다. types로 측면을 좁힐 수 있으나 필수는 아니다 — 미지정이면 전체를 최신순으로 준다. 전체가
    많을 수 있으니 limit/offset으로 페이지를 넘긴다. 반환의 total은 조건에 맞는 전체 수, has_more=true면
    offset을 늘려 더 가져올 수 있다. reviews가 비고 total=0이면 해당 조건의 강의평이 없는 것 —
    없는 내용을 지어내지 말 것. found=false면 강의 자체가 없음."""
    with Session(engine) as s:
        return tools.get_reviews_all(s, offering_id, types=types, limit=limit, offset=offset)


@mcp.tool
def get_professor(
    professor_id: Annotated[str | None, Field(description="교수 ID로 조회.")] = None,
    name: Annotated[str | None, Field(description="교수 이름으로 조회.")] = None,
) -> dict:
    """교수 정보(소속·종합 프로필·대표 강의평·개설 강의 목록)를 반환한다.

    profile은 그 교수의 강의 운영·평가 경향과 학생 평을 종합한 4개 항목
    (format·evaluation·reviews_summary·caveats)이다. 아직 종합 프로필이 없는 교수면 profile=null과
    profile_note가 온다. professor_id 또는 name 중 하나로 조회한다. name에 동명이 여럿이면
    candidates 배열로 후보를 돌려주니, 그 경우 id로 다시 호출하라. found=false면 해당 교수가 없음."""
    with Session(engine) as s:
        return tools.get_professor(s, professor_id=professor_id, name=name)


@mcp.tool(description=_RECOMMEND_DESC)
def recommend_courses(
    query: Annotated[str, Field(description="원하는 강의에 대한 자연어 설명 (예: '과제 적고 학점 잘 주는 과목').")],
    offering_ids: Annotated[
        list[str],
        Field(description="추천 후보 강의 ID 목록 — search_courses 결과의 offering_id들. 이 후보 안에서만 랭킹한다."),
    ],
) -> dict:
    """후보 list 기반 강의 추천 (설명은 _RECOMMEND_DESC)."""
    with Session(engine) as s:
        return tools.recommend_courses(s, query, offering_ids)