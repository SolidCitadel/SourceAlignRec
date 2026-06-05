import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { getOffering } from '../api/offerings';
import * as reviewsApi from '../api/reviews';
import { useWorkspaceStore } from '../stores/workspaceStore';
import type { OfferingDetail } from '../types/domain';
import { Button } from './Button';
import styles from './ReviewModal.module.css';

const TERM_OPTIONS = ['2026-1', '2025-2', '2025-1', '2024-2', '2024-1', '2023-2'];

export function ReviewModal() {
  const offeringId = useWorkspaceStore((s) => s.reviewModalOfferingId);
  if (!offeringId) return null;
  // key remount로 offeringId 변경 시 text/term/detail state 초기화.
  return <ReviewModalInner key={offeringId} offeringId={offeringId} />;
}

function ReviewModalInner({ offeringId }: { offeringId: string }) {
  const close = useWorkspaceStore((s) => s.closeReviewModal);
  const queryClient = useQueryClient();
  const [text, setText] = useState('');
  const [term, setTerm] = useState<string>(TERM_OPTIONS[1]);
  const [detail, setDetail] = useState<OfferingDetail | null>(null);

  const mutation = useMutation({
    mutationFn: () => reviewsApi.create(offeringId, { term, text: text.trim() }),
    onSuccess: () => {
      // 등록 리뷰는 unprocessed로 즉시 목록에 노출 — 해당 offering 리뷰 캐시 무효화.
      queryClient.invalidateQueries({ queryKey: ['offering-reviews', offeringId] });
      close();
    },
  });

  useEffect(() => {
    let cancelled = false;
    getOffering(offeringId).then(
      (d) => {
        if (!cancelled) setDetail(d);
      },
      () => {
        if (!cancelled) setDetail(null);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [offeringId]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') close();
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [close]);

  if (!detail) return null;

  const canSubmit = text.trim().length >= 10 && !mutation.isPending;

  const submit = () => {
    if (text.trim().length < 10 || mutation.isPending) return;
    mutation.mutate();
  };

  return (
    <div className={styles.overlay} onClick={close} role="presentation">
      <div
        className={styles.modal}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="리뷰 작성"
      >
        <header className={styles.header}>
          <div className={styles.title}>리뷰 작성</div>
          <button
            type="button"
            className={styles.closeBtn}
            onClick={close}
            aria-label="닫기"
          >
            ×
          </button>
        </header>

        <div className={styles.body}>
          <div className={styles.subjectRow}>
            <div className={styles.subjectName}>
              {detail.courseName} · {detail.professorName}
            </div>
            <div className={styles.termRow}>
              <label className={styles.termLabel} htmlFor="review-term">
                학기
              </label>
              <select
                id="review-term"
                className={styles.termSelect}
                value={term}
                onChange={(e) => setTerm(e.target.value)}
              >
                {TERM_OPTIONS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className={styles.fieldWrap}>
            <label className={styles.fieldLabel} htmlFor="review-body">
              리뷰
            </label>
            <textarea
              id="review-body"
              className={styles.textarea}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="채점, 시험, 과제, 팀플 등 본인의 경험을 솔직하게 적어주세요..."
              rows={8}
            />
            <div className={styles.helper}>
              다른 리뷰는 작성 중 노출되지 않아요 — anchoring 방지
            </div>
          </div>

          {mutation.isError && (
            <div className={styles.error} role="alert">
              등록에 실패했어요. 잠시 후 다시 시도해주세요.
            </div>
          )}

          <div className={styles.actions}>
            <Button size="sm" onClick={close} disabled={mutation.isPending}>
              취소
            </Button>
            <Button size="sm" variant="primary" onClick={submit} disabled={!canSubmit}>
              {mutation.isPending ? '제출 중…' : '제출'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
