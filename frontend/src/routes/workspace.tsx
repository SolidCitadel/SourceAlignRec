import { useState } from 'react';
import {
  AIPanel,
  Chip,
  ModeTabs,
  OfferingDetailPanel,
  ScheduleGrid,
  ScheduleSelector,
  SearchPanel,
  TopBar,
  Wishlist,
  WishlistRail,
} from '../components';
import {
  useActiveTimetable,
  useWishlistView,
  useWorkspaceStore,
} from '../stores/workspaceStore';
import type { OfferingSearchResultView, WishlistItemView } from '../types/domain';
import styles from './workspace.module.css';

export function Workspace() {
  const mode = useWorkspaceStore((s) => s.mode);
  const setMode = useWorkspaceStore((s) => s.setMode);
  const wishOpen = useWorkspaceStore((s) => s.wishOpen);
  const setWishOpen = useWorkspaceStore((s) => s.setWishOpen);
  const timeCompatible = useWorkspaceStore((s) => s.timeCompatible);
  const toggleTimeCompatible = useWorkspaceStore((s) => s.toggleTimeCompatible);
  const hideCompleted = useWorkspaceStore((s) => s.hideCompleted);
  const toggleHideCompleted = useWorkspaceStore((s) => s.toggleHideCompleted);
  const addToActiveTimetable = useWorkspaceStore((s) => s.addToActiveTimetable);
  const removeFromActiveTimetable = useWorkspaceStore((s) => s.removeFromActiveTimetable);
  const removeFromWishlist = useWorkspaceStore((s) => s.removeFromWishlist);
  const aiOpen = useWorkspaceStore((s) => s.aiOpen);
  const openAI = useWorkspaceStore((s) => s.openAI);
  const closeAI = useWorkspaceStore((s) => s.closeAI);
  const openOfferingDetail = useWorkspaceStore((s) => s.openOfferingDetail);
  const workspaceError = useWorkspaceStore((s) => s.workspaceError);
  const reloadWorkspace = useWorkspaceStore((s) => s.reloadWorkspace);

  const activeTimetable = useActiveTimetable();
  const { items: wishlistItems, hiddenByConflict: wishlistHidden } = useWishlistView();

  const [reloading, setReloading] = useState(false);
  const handleReload = async () => {
    setReloading(true);
    try {
      await reloadWorkspace();
    } finally {
      setReloading(false);
    }
  };

  const handleAdd = (item: WishlistItemView) => {
    // store가 duplicate·conflict 사전 검사 + API 호출 + alert 책임.
    addToActiveTimetable(item);
  };

  // AI가 열려있을 때 rail 클릭: AI 닫고 wishlist 펼침 (one-at-a-time 패턴)
  const expandWishlistFromRail = () => {
    closeAI();
    setWishOpen(true);
  };

  return (
    <div className={styles.shell}>
      <TopBar
        right={
          <>
            <Chip
              variant={hideCompleted ? 'active' : 'default'}
              onClick={toggleHideCompleted}
              style={{ cursor: 'pointer' }}
            >
              수료 숨김 {hideCompleted ? 'ON' : 'OFF'}
            </Chip>
            <Chip
              variant={timeCompatible ? 'active' : 'default'}
              onClick={toggleTimeCompatible}
              style={{ cursor: 'pointer' }}
            >
              충돌 숨김 {timeCompatible ? 'ON' : 'OFF'}
            </Chip>
          </>
        }
      >
        <Chip variant="soft">학기 · 2026-2</Chip>
        <ScheduleSelector />
      </TopBar>
      <div className={styles.body}>
        {workspaceError ? (
          <div className={styles.loadError}>
            <p className={styles.loadErrorText}>워크스페이스 데이터를 불러오지 못했습니다.</p>
            <button
              type="button"
              className={styles.loadErrorButton}
              onClick={handleReload}
              disabled={reloading}
            >
              {reloading ? '불러오는 중…' : '다시 시도'}
            </button>
          </div>
        ) : (
          <>
        {wishOpen ? (
          <Wishlist
            open={wishOpen}
            items={wishlistItems}
            hiddenByConflict={wishlistHidden}
            onClose={() => setWishOpen(false)}
            onItemClick={handleAdd}
            onItemRemove={(it) => removeFromWishlist(it.id)}
          />
        ) : (
          // 닫힘 시 항상 Rail (AI 진입 / 직접 닫기 통일).
          <WishlistRail count={wishlistItems.length} onExpand={expandWishlistFromRail} />
        )}
        <main className={styles.right}>
          <ModeTabs active={mode} onChange={setMode} />
          <div className={styles.content}>
            {mode === '시간표 짜기' ? (
              <ScheduleGrid
                timetable={activeTimetable}
                onRemoveCourse={removeFromActiveTimetable}
              />
            ) : (
              <SearchPanel
                onCardClick={(r: OfferingSearchResultView) => openOfferingDetail(r.id)}
                onAIClick={openAI}
              />
            )}
          </div>
          <OfferingDetailPanel />
        </main>
        {aiOpen && <AIPanel onCardClick={openOfferingDetail} />}
          </>
        )}
      </div>
    </div>
  );
}
