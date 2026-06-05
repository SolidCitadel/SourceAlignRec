import type { SignupForm, User } from '../../types/domain';
import type { AuthResponse, LoginRequest, ProfilePatch } from '../auth';
import { ApiError, getToken } from '../client';

const MOCK_TOKEN = 'mock-token';
const STORAGE_KEY = 'sar.mock.user';

function loadStoredUser(): User | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

function storeUser(user: User): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
}

export async function mockSignup(form: SignupForm): Promise<AuthResponse> {
  const user: User = {
    id: `u-${form.email}`,
    email: form.email,
    school: form.school,
    department: form.department,
    grade: form.grade,
    admissionYear: form.admissionYear,
    name: form.name,
    role: 'student',
  };
  storeUser(user);
  return { token: MOCK_TOKEN, user };
}

export async function mockLogin(input: LoginRequest): Promise<AuthResponse> {
  if (!input.email.trim() || !input.password.trim()) {
    throw new ApiError(401, '이메일 또는 비밀번호가 올바르지 않습니다.');
  }
  const stored = loadStoredUser();
  const user: User = stored && stored.email === input.email
    ? stored
    : {
        id: `u-${input.email}`,
        email: input.email,
        school: '경희대학교',
        department: '컴퓨터공학과',
        grade: 3,
        admissionYear: 2023,
        name: null,
        role: 'student',
      };
  storeUser(user);
  return { token: MOCK_TOKEN, user };
}

export async function mockMe(): Promise<User> {
  // real API와 동작 일치: token 없으면 401 (logout 후 hydrate 시 currentUser null로 ready).
  if (!getToken()) throw new ApiError(401, '인증이 필요합니다.');
  const user = loadStoredUser();
  if (!user) throw new ApiError(401, '인증이 만료되었습니다.');
  return user;
}

export async function mockUpdateMe(patch: ProfilePatch): Promise<User> {
  if (!getToken()) throw new ApiError(401, '인증이 필요합니다.');
  const user = loadStoredUser();
  if (!user) throw new ApiError(401, '인증이 만료되었습니다.');
  const updated: User = { ...user, ...patch };
  storeUser(updated);
  return updated;
}
