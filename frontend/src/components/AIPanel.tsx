import { useEffect, useRef, useState } from 'react';
import {
  useSearchResults,
  useWorkspaceStore,
} from '../stores/workspaceStore';
import type {
  ChatMessage,
  RecommendationCard,
} from '../types/domain';
import { formatMeetings, lastDeptSegment } from '../utils/format';
import styles from './AIPanel.module.css';

interface AIPanelProps {
  onCardClick: (offeringId: string) => void;
}

export function AIPanel({ onCardClick }: AIPanelProps) {
  const messages = useWorkspaceStore((s) => s.aiMessages);
  const loading = useWorkspaceStore((s) => s.aiLoading);
  const closeAI = useWorkspaceStore((s) => s.closeAI);
  const newAIThread = useWorkspaceStore((s) => s.newAIThread);
  const sendAIQuery = useWorkspaceStore((s) => s.sendAIQuery);
  const followUp = useWorkspaceStore((s) => s.followUp);
  // 추천 모집단 = 현재 페이지가 아니라 검색에 걸린 강의 전체.
  const { allVisible: candidates } = useSearchResults();

  const [draft, setDraft] = useState('');
  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [messages, loading]);

  const send = () => {
    if (!draft.trim()) return;
    if (messages.length === 0) {
      // 첫 query → recommend
      sendAIQuery(draft, candidates);
    } else {
      // 후속 질문 → 직전 추천 카드에 한정 grounding (store가 추천 id 추출)
      followUp(draft);
    }
    setDraft('');
  };

  return (
    <aside className={styles.panel}>
      <header className={styles.header}>
        <div className={styles.title}>
          <svg width="14" height="14" viewBox="0 0 13 13" fill="none" aria-hidden="true">
            <path
              d="M6.5 1 L7.7 5.3 L12 6.5 L7.7 7.7 L6.5 12 L5.3 7.7 L1 6.5 L5.3 5.3 Z"
              fill="var(--color-primary)"
            />
          </svg>
          AI 추천
        </div>
        <div className={styles.headerActions}>
          <button
            type="button"
            className={styles.newThreadLink}
            onClick={newAIThread}
            title="새 추천 시작"
          >
            + 새 추천
          </button>
          <button
            type="button"
            className={styles.iconBtn}
            onClick={closeAI}
            title="AI 패널 닫기"
            aria-label="AI 패널 닫기"
          >
            ×
          </button>
        </div>
      </header>

      <div className={styles.thread} ref={threadRef}>
        {messages.length === 0 && !loading && (
          <div className={styles.empty}>
            어떤 과목을 찾으시나요?
            <br />
            지금 검색한 강의들 중에서 골라 추천해드려요.
          </div>
        )}
        {messages.map((m) => (
          <MessageView key={m.id} message={m} onCardClick={onCardClick} />
        ))}
        {loading && (
          <div className={styles.loading}>
            <span className={styles.loadingDot} />
            <span className={styles.loadingDot} />
            <span className={styles.loadingDot} />
          </div>
        )}
      </div>

      <div className={styles.inputBar}>
        <div className={styles.inputPill}>
          <textarea
            className={styles.textarea}
            value={draft}
            placeholder={
              messages.length === 0
                ? '예: 과제 적고 시험 비중 낮은 거?'
                : '추천 카드에 대해 더 물어보세요'
            }
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
          />
          <button
            type="button"
            className={styles.sendBtn}
            onClick={send}
            disabled={!draft.trim() || loading}
            aria-label="보내기"
          >
            →
          </button>
        </div>
        <div className={styles.inputHint}>
          지금 검색한 강의들 중에서 추천해드려요
        </div>
      </div>
    </aside>
  );
}

function MessageView({
  message,
  onCardClick,
}: {
  message: ChatMessage;
  onCardClick: (offeringId: string) => void;
}) {
  if (message.role === 'user') {
    return <div className={styles.bubbleUser}>{message.text}</div>;
  }
  if (message.kind === 'notice') {
    return <div className={styles.notice}>{message.text}</div>;
  }
  if (message.kind === 'explanation') {
    return <div className={styles.bubbleAi}>{message.text}</div>;
  }
  // recommend
  return (
    <div className={styles.recStack}>
      {message.recommendations.map((rec) => (
        <RecCard key={`${message.id}-${rec.rank}`} rec={rec} onClick={() => onCardClick(rec.offeringId)} />
      ))}
    </div>
  );
}

function RecCard({ rec, onClick }: { rec: RecommendationCard; onClick: () => void }) {
  const wishlist = useWorkspaceStore((s) => s.wishlist);
  const addToWishlist = useWorkspaceStore((s) => s.addToWishlist);
  const removeFromWishlist = useWorkspaceStore((s) => s.removeFromWishlist);
  const inWishlist = wishlist.some((w) => w.id === rec.offeringId);
  const isTop = rec.rank === 1;

  // 카드 클릭 시 상세 진입 (single source). 내부 버튼은 propagation 차단.
  return (
    <div
      className={[styles.recCard, isTop ? styles.recCardTop : ''].filter(Boolean).join(' ')}
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      }}
    >
      <div className={styles.recHeader}>
        <span className={styles.recRank}>#{rec.rank}</span>
        <span className={styles.recName}>{rec.courseName}</span>
      </div>
      <div className={styles.recMeta}>
        {rec.professorName} · {lastDeptSegment(rec.department)}
      </div>
      <div className={styles.recMeta}>
        {rec.credit}학점 · {rec.type} · {formatMeetings(rec.meetings)}
      </div>
      <div className={styles.recRationale}>{rec.rationale}</div>
      <div className={styles.recActions}>
        <button
          type="button"
          className={[styles.wishBtn, inWishlist ? styles.wishBtnActive : ''].filter(Boolean).join(' ')}
          onClick={(e) => {
            e.stopPropagation();
            if (inWishlist) {
              removeFromWishlist(rec.offeringId);
            } else {
              addToWishlist({
                id: rec.offeringId,
                courseName: rec.courseName,
                professorName: rec.professorName,
                credit: rec.credit,
                type: rec.type,
                meetings: rec.meetings,
              });
            }
          }}
        >
          {inWishlist ? '✓ 담김' : '+ Wishlist'}
        </button>
      </div>
    </div>
  );
}
