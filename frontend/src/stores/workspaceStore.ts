import { useEffect, useMemo, useState } from 'react';
import { create, type StateCreator } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import * as authApi from '../api/auth';
import { ApiError, clearToken, setToken } from '../api/client';
import * as historyApi from '../api/history';
import * as recommendApi from '../api/recommend';
import * as requirementsApi from '../api/requirements';
import * as searchApi from '../api/search';
import * as timetablesApi from '../api/timetables';
import * as wishlistApi from '../api/wishlist';
import type {
  ChatMessage,
  ClassMeeting,
  GraduationProgress,
  GraduationRequirement,
  HistoryEntry,
  OfferingSearchResult,
  OfferingSearchResultView,
  RecommendationCard,
  RequirementCategory,
  SearchFilter,
  SignupForm,
  SortKey,
  Timetable,
  User,
  WishlistItem,
  WishlistItemView,
  WorkspaceMode,
} from '../types/domain';
import { ATTR_VALUES } from '../types/domain';

export const SEARCH_PAGE_SIZE = 10;

// === UI slice ===

interface UISlice {
  mode: WorkspaceMode;
  wishOpen: boolean;
  timeCompatible: boolean;
  /** '수료 숨김' — 본인 수강이력 과목(taken)을 검색에서 숨김. 기본 ON(재수강 시 OFF로 복원). */
  hideCompleted: boolean;
  setMode: (m: WorkspaceMode) => void;
  setWishOpen: (v: boolean) => void;
  toggleTimeCompatible: () => void;
  toggleHideCompleted: () => void;
}

const createUISlice: StateCreator<Store, [], [], UISlice> = (set) => ({
  mode: '시간표 짜기',
  wishOpen: true,
  timeCompatible: true,
  hideCompleted: true,
  setMode: (mode) => set({ mode }),
  setWishOpen: (open) => set({ wishOpen: open }),
  toggleTimeCompatible: () => set((s) => ({ timeCompatible: !s.timeCompatible })),
  toggleHideCompleted: () => set((s) => ({ hideCompleted: !s.hideCompleted })),
});

// === Timetable slice ===
//
// 모든 mutation은 백엔드 응답 후 store 갱신 (optimistic update 미도입 — prototype 단순화).
// 에러는 store mutator 안에서 alert로 표면화 — 호출부 fire-and-forget OK.

interface TimetableSlice {
  timetables: Timetable[];
  activeTimetableId: string;
  setActiveTimetable: (id: string) => void;
  newTimetable: () => Promise<void>;
  duplicateActiveTimetable: () => Promise<void>;
  deleteTimetable: (id: string) => Promise<void>;
  addToActiveTimetable: (item: WishlistItem) => Promise<void>;
  removeFromActiveTimetable: (courseId: string) => Promise<void>;
}

function meetingsOverlap(a: ClassMeeting, b: ClassMeeting): boolean {
  if (a.day !== b.day) return false;
  return a.startTime < b.endTime && b.startTime < a.endTime;
}

function findConflict(item: WishlistItem, timetable: Timetable): string | null {
  for (const c of timetable.courses) {
    if (c.id === item.id) continue;
    for (const m1 of item.meetings) {
      for (const m2 of c.meetings) {
        if (meetingsOverlap(m1, m2)) return c.courseName;
      }
    }
  }
  return null;
}

function alertError(err: unknown, fallback: string): void {
  alert(err instanceof ApiError ? err.detail : fallback);
}

const createTimetableSlice: StateCreator<Store, [], [], TimetableSlice> = (set, get) => ({
  timetables: [],
  activeTimetableId: '',
  setActiveTimetable: (id) => set({ activeTimetableId: id }),
  newTimetable: async () => {
    try {
      const { timetable } = await timetablesApi.create();
      set((s) => ({
        timetables: [...s.timetables, timetable],
        activeTimetableId: timetable.id,
      }));
    } catch (err) {
      alertError(err, '시간표 생성에 실패했습니다.');
    }
  },
  duplicateActiveTimetable: async () => {
    const s = get();
    if (!s.activeTimetableId) return;
    try {
      const { timetable } = await timetablesApi.duplicate(s.activeTimetableId);
      set((state) => ({
        timetables: [...state.timetables, timetable],
        activeTimetableId: timetable.id,
      }));
    } catch (err) {
      alertError(err, '시간표 복제에 실패했습니다.');
    }
  },
  deleteTimetable: async (id) => {
    // client guard. backend도 409 fallback.
    if (get().timetables.length <= 1) return;
    try {
      await timetablesApi.remove(id);
      set((state) => {
        const remaining = state.timetables.filter((t) => t.id !== id);
        const nextActiveId =
          state.activeTimetableId === id ? remaining[0].id : state.activeTimetableId;
        return { timetables: remaining, activeTimetableId: nextActiveId };
      });
    } catch (err) {
      alertError(err, '시간표 삭제에 실패했습니다.');
    }
  },
  addToActiveTimetable: async (item) => {
    const s = get();
    const active = s.timetables.find((t) => t.id === s.activeTimetableId);
    if (!active) return;
    if (active.courses.some((c) => c.id === item.id)) {
      alert('이미 등록된 과목입니다.');
      return;
    }
    const conflictWith = findConflict(item, active);
    if (conflictWith) {
      alert(`시간 충돌: ${conflictWith}`);
      return;
    }
    try {
      const { course } = await timetablesApi.addCourse(active.id, item.id);
      set((state) => ({
        timetables: state.timetables.map((t) =>
          t.id === active.id ? { ...t, courses: [...t.courses, course] } : t,
        ),
      }));
    } catch (err) {
      alertError(err, '시간표 추가에 실패했습니다.');
    }
  },
  removeFromActiveTimetable: async (courseId) => {
    const activeId = get().activeTimetableId;
    if (!activeId) return;
    try {
      await timetablesApi.removeCourse(activeId, courseId);
      set((state) => ({
        timetables: state.timetables.map((t) =>
          t.id === activeId
            ? { ...t, courses: t.courses.filter((c) => c.id !== courseId) }
            : t,
        ),
      }));
    } catch (err) {
      alertError(err, '시간표에서 제거하지 못했습니다.');
    }
  },
});

// === Wishlist slice ===

interface WishlistSlice {
  wishlist: WishlistItem[];
  addToWishlist: (item: WishlistItem) => Promise<void>;
  removeFromWishlist: (id: string) => Promise<void>;
}

const createWishlistSlice: StateCreator<Store, [], [], WishlistSlice> = (set) => ({
  wishlist: [],
  addToWishlist: async (item) => {
    try {
      // server는 idempotent — hydrate된 item을 echo.
      const { item: added } = await wishlistApi.add(item.id);
      set((s) =>
        s.wishlist.some((w) => w.id === added.id)
          ? {}
          : { wishlist: [...s.wishlist, added] },
      );
    } catch (err) {
      alertError(err, 'Wishlist 추가에 실패했습니다.');
    }
  },
  removeFromWishlist: async (id) => {
    try {
      await wishlistApi.remove(id);
      set((s) => ({ wishlist: s.wishlist.filter((i) => i.id !== id) }));
    } catch (err) {
      alertError(err, 'Wishlist 제거에 실패했습니다.');
    }
  },
});

// === Search slice ===

export const CREDIT_OPTIONS: number[] = [0, 1, 2, 3];

/** chip default: 모든 값 ON. department=''=본인 학과 자동 (백엔드 resolve).
 *  courseTypes는 학과별 동적 라벨(/departments)이라 default []=전체 (선택 학과 라벨은 FilterSidebar가 렌더). */
export function defaultSearchFilter(): SearchFilter {
  return {
    department: '',
    courseTypes: [],
    credits: [...CREDIT_OPTIONS],
    keyword: '',
    englishOnly: false,
    attributes: {
      grading: [...ATTR_VALUES.grading],
      assignment: [...ATTR_VALUES.assignment],
      teamProject: [...ATTR_VALUES.teamProject],
      examWeight: [...ATTR_VALUES.examWeight],
      attendance: [...ATTR_VALUES.attendance],
    },
  };
}

/** 모든 chip OFF (필터 강함). resetSearchFilter UX 별도. */
export const emptySearchFilter: SearchFilter = {
  department: '',
  courseTypes: [],
  credits: [],
  keyword: '',
  englishOnly: false,
  attributes: { grading: [], assignment: [], teamProject: [], examWeight: [], attendance: [] },
};

interface SearchSlice {
  searchFilter: SearchFilter;
  searchSort: SortKey;
  searchPage: number;
  setSearchFilter: (filter: SearchFilter) => void;
  patchSearchFilter: (patch: Partial<SearchFilter>) => void;
  resetSearchFilter: () => void;
  setSearchSort: (sort: SortKey) => void;
  setSearchPage: (page: number) => void;
}

const createSearchSlice: StateCreator<Store, [], [], SearchSlice> = (set) => ({
  // 초기값: 미인증 상태 — 빈 filter. authReady + currentUser 채워지면 컴포넌트가 patchSearchFilter로 default 적용.
  searchFilter: emptySearchFilter,
  searchSort: 'course_name',
  searchPage: 1,
  setSearchFilter: (filter) => set({ searchFilter: filter, searchPage: 1 }),
  patchSearchFilter: (patch) =>
    set((s) => ({ searchFilter: { ...s.searchFilter, ...patch }, searchPage: 1 })),
  resetSearchFilter: () => set({ searchFilter: emptySearchFilter, searchPage: 1 }),
  setSearchSort: (sort) => set({ searchSort: sort, searchPage: 1 }),
  setSearchPage: (page) => set({ searchPage: page }),
});

// === AI slice ===

interface AISlice {
  aiOpen: boolean;
  aiMessages: ChatMessage[];
  aiLoading: boolean;
  /** AI 열기 직전의 wishOpen 상태 — 닫을 때 복원용. */
  aiWishWasOpen: boolean;
  openAI: () => void;
  closeAI: () => void;
  newAIThread: () => void;
  sendAIQuery: (query: string, shortlist: OfferingSearchResult[]) => Promise<void>;
  followUp: (query: string) => Promise<void>;
}

// 추천 카드를 assistant 턴 텍스트로 렌더 — 사용자가 본 추천(과목·교수·rationale)을 대화에 그대로 보존.
// offering_id 포함: converse 백엔드가 tool 조회 대상을 매핑하는 데 사용.
function renderRecommendTurn(recs: RecommendationCard[]): string {
  const lines = ['다음 과목을 추천했습니다:'];
  for (const r of [...recs].sort((a, b) => a.rank - b.rank)) {
    lines.push(`${r.rank}. ${r.courseName} (${r.professorName}) [${r.offeringId}]\n   ${r.rationale}`);
  }
  return lines.join('\n');
}

function toChatTurns(messages: ChatMessage[]): recommendApi.ChatTurn[] {
  const turns: recommendApi.ChatTurn[] = [];
  for (const m of messages) {
    if (m.role === 'user') turns.push({ role: 'user', content: m.text });
    else if (m.kind === 'recommend')
      turns.push({ role: 'assistant', content: renderRecommendTurn(m.recommendations) });
    else if (m.kind === 'explanation' || m.kind === 'notice')
      turns.push({ role: 'assistant', content: m.text });
  }
  return turns;
}

// 후속 질문 대상 = 가장 최근 추천 카드의 offering id(rank 순). 백엔드 grounding·tool 조회 범위.
function lastRecommendedOfferingIds(messages: ChatMessage[]): string[] {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role === 'assistant' && m.kind === 'recommend') {
      return [...m.recommendations].sort((a, b) => a.rank - b.rank).map((r) => r.offeringId);
    }
  }
  return [];
}

const createAISlice: StateCreator<Store, [], [], AISlice> = (set, get) => ({
  aiOpen: false,
  aiMessages: [],
  aiLoading: false,
  aiWishWasOpen: true,
  openAI: () =>
    set((s) => ({
      aiOpen: true,
      aiWishWasOpen: s.wishOpen,
      wishOpen: false,
    })),
  // panel hide만 — 메시지 유지. (wishlist 토글 같은 layout-driven hide와 명시적 종료를 구분.)
  closeAI: () =>
    set((s) => ({
      aiOpen: false,
      wishOpen: s.aiWishWasOpen,
    })),
  newAIThread: () => set({ aiMessages: [] }),
  sendAIQuery: async (query, shortlist) => {
    const trimmed = query.trim();
    if (!trimmed) return;
    const userMsg: ChatMessage = { id: `m${Date.now()}-u`, role: 'user', text: trimmed };
    set((s) => ({ aiMessages: [...s.aiMessages, userMsg], aiLoading: true }));

    if (shortlist.length === 0) {
      const notice: ChatMessage = {
        id: `m${Date.now()}-n`,
        role: 'assistant',
        kind: 'notice',
        text: '검색 결과가 비어 있어 추천할 수 없습니다. 필터를 완화해보세요.',
      };
      set((s) => ({ aiMessages: [...s.aiMessages, notice], aiLoading: false }));
      return;
    }

    try {
      const res = await recommendApi.recommend({
        mode: 'initial',
        query: trimmed,
        candidateOfferingIds: shortlist.map((r) => r.id),
        messages: [],
      });
      if (res.recommendations) {
        const aiMsg: ChatMessage = {
          id: `m${Date.now()}-a`,
          role: 'assistant',
          kind: 'recommend',
          recommendations: res.recommendations,
        };
        set((s) => ({ aiMessages: [...s.aiMessages, aiMsg], aiLoading: false }));
      } else {
        set({ aiLoading: false });
      }
    } catch (err) {
      const notice: ChatMessage = {
        id: `m${Date.now()}-err`,
        role: 'assistant',
        kind: 'notice',
        text: err instanceof ApiError ? err.detail : '추천 생성 중 오류가 발생했습니다.',
      };
      set((s) => ({ aiMessages: [...s.aiMessages, notice], aiLoading: false }));
    }
  },
  followUp: async (query) => {
    const trimmed = query.trim();
    if (!trimmed) return;
    const recommendedOfferingIds = lastRecommendedOfferingIds(get().aiMessages);
    const priorTurns = toChatTurns(get().aiMessages);
    const userMsg: ChatMessage = { id: `m${Date.now()}-u`, role: 'user', text: trimmed };
    set((s) => ({ aiMessages: [...s.aiMessages, userMsg], aiLoading: true }));

    // 추천 이력이 없으면 grounding 대상이 없음 — 백엔드 400 전에 클라이언트에서 안내.
    if (recommendedOfferingIds.length === 0) {
      const notice: ChatMessage = {
        id: `m${Date.now()}-n`,
        role: 'assistant',
        kind: 'notice',
        text: '먼저 추천을 받은 뒤 후속 질문을 해주세요.',
      };
      set((s) => ({ aiMessages: [...s.aiMessages, notice], aiLoading: false }));
      return;
    }

    try {
      const res = await recommendApi.recommend({
        mode: 'converse',
        query: trimmed,
        recommendedOfferingIds,
        messages: [...priorTurns, { role: 'user', content: trimmed }],
      });
      if (res.explanation) {
        const aiMsg: ChatMessage = {
          id: `m${Date.now()}-e`,
          role: 'assistant',
          kind: 'explanation',
          text: res.explanation,
        };
        set((s) => ({ aiMessages: [...s.aiMessages, aiMsg], aiLoading: false }));
      } else {
        set({ aiLoading: false });
      }
    } catch (err) {
      const notice: ChatMessage = {
        id: `m${Date.now()}-err`,
        role: 'assistant',
        kind: 'notice',
        text: err instanceof ApiError ? err.detail : '응답 생성 중 오류가 발생했습니다.',
      };
      set((s) => ({ aiMessages: [...s.aiMessages, notice], aiLoading: false }));
    }
  },
});

// === Detail slice ===

interface DetailSlice {
  detailOfferingId: string | null;
  openOfferingDetail: (id: string) => void;
  closeOfferingDetail: () => void;
}

const createDetailSlice: StateCreator<Store, [], [], DetailSlice> = (set) => ({
  detailOfferingId: null,
  openOfferingDetail: (id) => set({ detailOfferingId: id }),
  closeOfferingDetail: () => set({ detailOfferingId: null }),
});

// === Auth slice ===

export type LoginResult = { ok: true } | { ok: false; reason: 'invalid' | 'empty' };

interface AuthSlice {
  currentUser: User | null;
  /** 초기 hydrate 완료 여부. false면 가드가 진입 결정 보류 (flicker 방지). */
  authReady: boolean;
  /** 워크스페이스(위시리스트·시간표) fetch 실패 여부. true면 인증은 유지하되 데이터 영역만 에러 표시. */
  workspaceError: boolean;
  login: (email: string, password: string) => Promise<LoginResult>;
  signup: (form: SignupForm) => Promise<void>;
  logout: () => void;
  /** 프로필 수정 → PATCH /me 영속 후 currentUser 갱신. 실패 시 throw(호출부가 처리). */
  updateProfile: (patch: authApi.ProfilePatch) => Promise<void>;
  /** 부팅 시 호출. localStorage token으로 /me 조회해 currentUser 복원. */
  hydrateAuth: () => Promise<void>;
  /** 워크스페이스 데이터 재요청 (workspaceError 상태에서 재시도). */
  reloadWorkspace: () => Promise<void>;
}

// 인증 직후·hydrate 시점에 wishlist + timetables 동시 fetch.
// 각각 실패해도 빈 list로 진행 — 인증 결과를 deny하지 않음.
// 단, 실패 여부를 error로 surface해 워크스페이스 영역에서 에러 표시·재시도하게 한다
// (조용히 빈 list로 두면 정상 상태와 구분 불가 → 화이트스크린/데이터 유실 오인).
async function fetchUserWorkspace(): Promise<{
  wishlist: WishlistItem[];
  timetables: Timetable[];
  history: HistoryEntry[];
  requirements: GraduationRequirement[];
  gradTotalRequired: number | null;
  error: boolean;
}> {
  const [wlRes, ttRes, hRes, rRes] = await Promise.allSettled([
    wishlistApi.list(),
    timetablesApi.list(),
    historyApi.list(),
    requirementsApi.list(),
  ]);
  return {
    wishlist: wlRes.status === 'fulfilled' ? wlRes.value.items : [],
    timetables: ttRes.status === 'fulfilled' ? ttRes.value.timetables : [],
    history: hRes.status === 'fulfilled' ? hRes.value.items : [],
    requirements: rRes.status === 'fulfilled' ? rRes.value.items : [],
    gradTotalRequired: rRes.status === 'fulfilled' ? rRes.value.totalRequired : null,
    error:
      wlRes.status === 'rejected' ||
      ttRes.status === 'rejected' ||
      hRes.status === 'rejected' ||
      rRes.status === 'rejected',
  };
}

const createAuthSlice: StateCreator<Store, [], [], AuthSlice> = (set, get) => ({
  currentUser: null,
  authReady: false,
  workspaceError: false,
  login: async (email, password) => {
    if (!email.trim() || !password.trim()) return { ok: false, reason: 'empty' };
    try {
      const { token, user } = await authApi.login({ email, password });
      setToken(token);
      const ws = await fetchUserWorkspace();
      set({
        currentUser: user,
        searchFilter: defaultSearchFilter(),
        wishlist: ws.wishlist,
        timetables: ws.timetables,
        history: ws.history,
        requirements: ws.requirements,
        gradTotalRequired: ws.gradTotalRequired,
        activeTimetableId: ws.timetables[0]?.id ?? '',
        workspaceError: ws.error,
      });
      return { ok: true };
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return { ok: false, reason: 'invalid' };
      throw err;
    }
  },
  signup: async (form) => {
    const { token, user } = await authApi.signup(form);
    setToken(token);
    const ws = await fetchUserWorkspace();
    set({
      currentUser: user,
      searchFilter: defaultSearchFilter(),
      wishlist: ws.wishlist,
      timetables: ws.timetables,
      activeTimetableId: ws.timetables[0]?.id ?? '',
      workspaceError: ws.error,
    });
  },
  logout: () => {
    clearToken();
    set({
      currentUser: null,
      wishlist: [],
      timetables: [],
      history: [],
      requirements: [],
      gradTotalRequired: null,
      activeTimetableId: '',
      workspaceError: false,
    });
  },
  updateProfile: async (patch) => {
    const user = await authApi.updateMe(patch);
    set({ currentUser: user });
  },
  hydrateAuth: async () => {
    try {
      const user = await authApi.me();
      const ws = await fetchUserWorkspace();
      set({
        currentUser: user,
        authReady: true,
        searchFilter: defaultSearchFilter(),
        wishlist: ws.wishlist,
        timetables: ws.timetables,
        history: ws.history,
        requirements: ws.requirements,
        gradTotalRequired: ws.gradTotalRequired,
        activeTimetableId: ws.timetables[0]?.id ?? '',
        workspaceError: ws.error,
      });
    } catch {
      // token 없음 / 만료 / 백엔드 미가용 → 미인증 상태로 ready.
      clearToken();
      set({ currentUser: null, authReady: true });
    }
  },
  reloadWorkspace: async () => {
    const ws = await fetchUserWorkspace();
    // 재시도 성공 시 기존 활성 시간표 선택을 보존, 사라졌으면 첫 번째로.
    const prevActive = get().activeTimetableId;
    const stillExists = ws.timetables.some((t) => t.id === prevActive);
    set({
      wishlist: ws.wishlist,
      timetables: ws.timetables,
      history: ws.history,
      requirements: ws.requirements,
      gradTotalRequired: ws.gradTotalRequired,
      activeTimetableId: stillExists ? prevActive : (ws.timetables[0]?.id ?? ''),
      workspaceError: ws.error,
    });
  },
});

// === Review Modal slice ===

interface ReviewModalSlice {
  reviewModalOfferingId: string | null;
  openReviewModal: (offeringId: string) => void;
  closeReviewModal: () => void;
}

const createReviewModalSlice: StateCreator<Store, [], [], ReviewModalSlice> = (set) => ({
  reviewModalOfferingId: null,
  openReviewModal: (offeringId) => set({ reviewModalOfferingId: offeringId }),
  closeReviewModal: () => set({ reviewModalOfferingId: null }),
});

// === History slice ===

// timetable/wishlist와 동일: mutation은 백엔드 응답 후 store 갱신, 에러는 alert로 표면화.
// 초기 history/requirements는 fetchUserWorkspace가 로그인/hydrate 시 적재.
interface HistorySlice {
  history: HistoryEntry[];
  requirements: GraduationRequirement[];
  /** 졸업 총 이수학점(영역합과 별개의 스칼라). 미설정 시 null. */
  gradTotalRequired: number | null;
  addHistoryEntry: (entry: Omit<HistoryEntry, 'id'>) => Promise<void>;
  removeHistoryEntry: (id: string) => Promise<void>;
  patchRequirement: (category: RequirementCategory, required: number) => Promise<void>;
  addRequirement: (category: RequirementCategory, required: number) => Promise<void>;
  removeRequirement: (category: RequirementCategory) => Promise<void>;
  setGradTotalRequired: (required: number) => Promise<void>;
}

const createHistorySlice: StateCreator<Store, [], [], HistorySlice> = (set) => ({
  history: [],
  requirements: [],
  gradTotalRequired: null,
  addHistoryEntry: async (entry) => {
    try {
      const { item } = await historyApi.add(entry);
      set((s) => ({ history: [...s.history, item] }));
    } catch (err) {
      alertError(err, '수강 이력 추가에 실패했습니다.');
    }
  },
  removeHistoryEntry: async (id) => {
    try {
      await historyApi.remove(id);
      set((s) => ({ history: s.history.filter((e) => e.id !== id) }));
    } catch (err) {
      alertError(err, '수강 이력 삭제에 실패했습니다.');
    }
  },
  patchRequirement: async (category, required) => {
    try {
      const { item } = await requirementsApi.upsert(category, required);
      set((s) => ({
        requirements: s.requirements.map((r) => (r.category === item.category ? item : r)),
      }));
    } catch (err) {
      alertError(err, '졸업요건 수정에 실패했습니다.');
    }
  },
  addRequirement: async (category, required) => {
    try {
      const { item } = await requirementsApi.upsert(category, required);
      set((s) =>
        s.requirements.some((r) => r.category === item.category)
          ? { requirements: s.requirements.map((r) => (r.category === item.category ? item : r)) }
          : { requirements: [...s.requirements, item] },
      );
    } catch (err) {
      alertError(err, '졸업요건 추가에 실패했습니다.');
    }
  },
  removeRequirement: async (category) => {
    try {
      await requirementsApi.remove(category);
      set((s) => ({ requirements: s.requirements.filter((r) => r.category !== category) }));
    } catch (err) {
      alertError(err, '졸업요건 삭제에 실패했습니다.');
    }
  },
  setGradTotalRequired: async (required) => {
    try {
      const { totalRequired } = await requirementsApi.setTotal(required);
      set({ gradTotalRequired: totalRequired });
    } catch (err) {
      alertError(err, '졸업 총 이수학점 설정에 실패했습니다.');
    }
  },
});

// === Combined store ===

type Store = UISlice &
  TimetableSlice &
  WishlistSlice &
  SearchSlice &
  AISlice &
  DetailSlice &
  AuthSlice &
  ReviewModalSlice &
  HistorySlice;

// 추천 채팅(aiMessages)만 sessionStorage persist — 탭 닫으면 휘발, page reload·다른 탭 이동 시 유지.
// UI 상태(aiOpen 등)는 휘발 — reload 후 panel은 닫힌 채 진입하되 + 누르면 이전 chat 복원.
export const useWorkspaceStore = create<Store>()(
  persist(
    (...a) => ({
      ...createUISlice(...a),
      ...createTimetableSlice(...a),
      ...createWishlistSlice(...a),
      ...createSearchSlice(...a),
      ...createAISlice(...a),
      ...createDetailSlice(...a),
      ...createAuthSlice(...a),
      ...createReviewModalSlice(...a),
      ...createHistorySlice(...a),
    }),
    {
      name: 'sar.workspace',
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({ aiMessages: state.aiMessages }),
    },
  ),
);

// === Selector hooks ===

/**
 * 활성 시간표가 없을 때(로그인 직후 fetch 실패 등) 반환하는 sentinel.
 * 정상 사용자는 항상 시간표 ≥1개(signup 자동 생성 + 마지막 삭제 차단)이므로
 * 이 값은 fetch 실패 시에만 노출되며, 소비자가 .name/.courses에서 크래시하지 않게 한다.
 */
export const EMPTY_TIMETABLE: Timetable = Object.freeze({
  id: '',
  name: '—',
  courses: [],
});

export function useActiveTimetable(): Timetable {
  const timetables = useWorkspaceStore((s) => s.timetables);
  const activeId = useWorkspaceStore((s) => s.activeTimetableId);
  return useMemo(
    () => timetables.find((t) => t.id === activeId) ?? timetables[0] ?? EMPTY_TIMETABLE,
    [timetables, activeId],
  );
}

export interface WishlistView {
  items: WishlistItemView[];
  hiddenByConflict: number;
}

export function useWishlistView(): WishlistView {
  const wishlist = useWorkspaceStore((s) => s.wishlist);
  const activeTimetable = useActiveTimetable();
  const timeCompatible = useWorkspaceStore((s) => s.timeCompatible);
  return useMemo(() => {
    const annotated = wishlist.map((item) => {
      const inSchedule = activeTimetable.courses.some((c) => c.id === item.id);
      const hasConflict = !inSchedule && findConflict(item, activeTimetable) !== null;
      return { ...item, conflict: hasConflict, inSchedule };
    });
    if (!timeCompatible) {
      return { items: annotated, hiddenByConflict: 0 };
    }
    const items = annotated.filter((v) => !v.conflict);
    return { items, hiddenByConflict: annotated.length - items.length };
  }, [wishlist, activeTimetable, timeCompatible]);
}

// === Search selectors ===

export interface PagedSearchResults {
  /** 현재 페이지 슬라이스 (목록 렌더용). */
  items: OfferingSearchResultView[];
  /** 필터·토글 적용 후 전 페이지 통틀어 보이는 강의 전체 (AI 추천 모집단). */
  allVisible: OfferingSearchResultView[];
  total: number;
  hiddenByConflict: number;
  /** '수료 숨김' ON으로 가려진 수강 과목 수 (충돌로 가려진 건 제외 — 카운트 disjoint). */
  hiddenByTaken: number;
  page: number;
  pageCount: number;
  pageSize: number;
  loading: boolean;
}

// === History selectors ===

/**
 * 졸업 진행률 derive.
 * - F는 졸업 학점에서 제외. 그 외(P 포함)는 모두 합산.
 * - history.courseType은 졸업요건 카테고리에서 선택되므로 항상 같은 축 — 모든 카테고리 자동 합산.
 */
export function useGraduationProgress(): GraduationProgress {
  const history = useWorkspaceStore((s) => s.history);
  const requirements = useWorkspaceStore((s) => s.requirements);
  const gradTotalRequired = useWorkspaceStore((s) => s.gradTotalRequired);
  return useMemo(() => {
    const totals = new Map<string, number>();
    let total = 0;
    for (const e of history) {
      if (e.grade === 'F') continue;
      total += e.credits;
      totals.set(e.courseType, (totals.get(e.courseType) ?? 0) + e.credits);
    }
    return {
      totalCredits: total,
      gradTotalRequired,
      byCategory: requirements.map((r) => ({
        category: r.category,
        current: totals.get(r.category) ?? 0,
        required: r.required,
      })),
    };
  }, [history, requirements, gradTotalRequired]);
}

export function useHistoryByTerm(): { term: string; entries: HistoryEntry[]; credits: number }[] {
  const history = useWorkspaceStore((s) => s.history);
  return useMemo(() => {
    const groups = new Map<string, HistoryEntry[]>();
    for (const e of history) {
      if (!groups.has(e.term)) groups.set(e.term, []);
      groups.get(e.term)!.push(e);
    }
    return Array.from(groups.entries())
      .sort(([a], [b]) => b.localeCompare(a))
      .map(([term, entries]) => ({
        term,
        entries,
        credits: entries.filter((e) => e.grade !== 'F').reduce((s, e) => s + e.credits, 0),
      }));
  }, [history]);
}

export function useSearchResults(): PagedSearchResults {
  const filter = useWorkspaceStore((s) => s.searchFilter);
  const sort = useWorkspaceStore((s) => s.searchSort);
  const page = useWorkspaceStore((s) => s.searchPage);
  const wishlist = useWorkspaceStore((s) => s.wishlist);
  const activeTimetable = useActiveTimetable();
  const timeCompatible = useWorkspaceStore((s) => s.timeCompatible);
  const hideCompleted = useWorkspaceStore((s) => s.hideCompleted);

  // raw === null = 첫 fetch 미완. fetch 진행 중 stale 결과는 그대로 유지 (UX 자연스러움).
  const [raw, setRaw] = useState<OfferingSearchResult[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    searchApi.search({ filter, sort }).then(
      (res) => {
        if (!cancelled) setRaw(res.results);
      },
      () => {
        if (!cancelled) setRaw([]);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [filter, sort]);

  return useMemo(() => {
    const loading = raw === null;
    const list = raw ?? [];
    // 충돌·등록 annotate
    const wishIds = new Set(wishlist.map((w) => w.id));
    const annotated: OfferingSearchResultView[] = list.map((r) => {
      const inSchedule = activeTimetable.courses.some((c) => c.id === r.id);
      const hasConflict = !inSchedule && findConflict(r, activeTimetable) !== null;
      return { ...r, conflict: hasConflict, inSchedule, inWishlist: wishIds.has(r.id) };
    });

    // 시간 양립 ON 시 충돌 카드 hide
    const afterConflict = timeCompatible ? annotated.filter((v) => !v.conflict) : annotated;
    const hiddenByConflict = annotated.length - afterConflict.length;

    // 수료 숨김 ON 시 taken 카드 hide (충돌로 이미 가려진 건 제외 — 카운트 disjoint)
    const visible = hideCompleted ? afterConflict.filter((v) => !v.taken) : afterConflict;
    const hiddenByTaken = afterConflict.length - visible.length;

    const total = visible.length;
    const pageCount = Math.max(1, Math.ceil(total / SEARCH_PAGE_SIZE));
    const clampedPage = Math.min(Math.max(1, page), pageCount);
    const start = (clampedPage - 1) * SEARCH_PAGE_SIZE;
    const items = visible.slice(start, start + SEARCH_PAGE_SIZE);

    return {
      items,
      allVisible: visible,
      total,
      hiddenByConflict,
      hiddenByTaken,
      page: clampedPage,
      pageCount,
      pageSize: SEARCH_PAGE_SIZE,
      loading,
    };
  }, [raw, page, wishlist, activeTimetable, timeCompatible, hideCompleted]);
}
