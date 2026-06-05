// api-contract/timetable.md 정합. mock 분기 미도입.

import type { ScheduledCourse, Timetable } from '../types/domain';
import { apiDelete, apiGet, apiPatch, apiPost } from './client';

interface TimetablesResponse {
  timetables: Timetable[];
}

interface TimetableResponse {
  timetable: Timetable;
}

interface CourseResponse {
  course: ScheduledCourse;
}

export function list(): Promise<TimetablesResponse> {
  return apiGet<TimetablesResponse>('/timetables');
}

export function create(): Promise<TimetableResponse> {
  return apiPost<TimetableResponse>('/timetables');
}

export function rename(id: string, name: string): Promise<TimetableResponse> {
  return apiPatch<TimetableResponse>(`/timetables/${encodeURIComponent(id)}`, { name });
}

export function remove(id: string): Promise<void> {
  return apiDelete<void>(`/timetables/${encodeURIComponent(id)}`);
}

export function duplicate(id: string): Promise<TimetableResponse> {
  return apiPost<TimetableResponse>(`/timetables/${encodeURIComponent(id)}/duplicate`);
}

export function addCourse(timetableId: string, offeringId: string): Promise<CourseResponse> {
  return apiPost<CourseResponse>(
    `/timetables/${encodeURIComponent(timetableId)}/courses`,
    { offeringId },
  );
}

export function removeCourse(timetableId: string, offeringId: string): Promise<void> {
  return apiDelete<void>(
    `/timetables/${encodeURIComponent(timetableId)}/courses/${encodeURIComponent(offeringId)}`,
  );
}
