// api-contract/wishlist.md 정합. mock 분기 미도입 — wishlist는 backend 연결 필수 영역.

import type { WishlistItem } from '../types/domain';
import { apiDelete, apiGet, apiPost } from './client';

interface WishlistResponse {
  items: WishlistItem[];
}

interface WishlistItemResponse {
  item: WishlistItem;
}

export function list(): Promise<WishlistResponse> {
  return apiGet<WishlistResponse>('/wishlist');
}

export function add(offeringId: string): Promise<WishlistItemResponse> {
  return apiPost<WishlistItemResponse>('/wishlist', { offeringId });
}

export function remove(offeringId: string): Promise<void> {
  return apiDelete<void>(`/wishlist/${encodeURIComponent(offeringId)}`);
}
