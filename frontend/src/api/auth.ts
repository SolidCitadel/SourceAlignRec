import type { SignupForm, User } from '../types/domain';
import { apiGet, apiPatch, apiPost, USE_MOCK } from './client';
import { mockLogin, mockMe, mockSignup, mockUpdateMe } from './mock/auth';

/** 프로필 부분 수정. 보낸 필드만 반영. email·role은 변경 불가. */
export interface ProfilePatch {
  name?: string;
  school?: string;
  department?: string;
  grade?: number;
  admissionYear?: number;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface AuthResponse {
  token: string;
  user: User;
}

export function signup(form: SignupForm): Promise<AuthResponse> {
  if (USE_MOCK) return mockSignup(form);
  return apiPost<AuthResponse>('/auth/signup', form);
}

export function login(input: LoginRequest): Promise<AuthResponse> {
  if (USE_MOCK) return mockLogin(input);
  return apiPost<AuthResponse>('/auth/login', input);
}

export function me(): Promise<User> {
  if (USE_MOCK) return mockMe();
  return apiGet<User>('/me');
}

export function updateMe(patch: ProfilePatch): Promise<User> {
  if (USE_MOCK) return mockUpdateMe(patch);
  return apiPatch<User>('/me', patch);
}
