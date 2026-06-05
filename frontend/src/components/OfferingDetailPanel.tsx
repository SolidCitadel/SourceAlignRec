import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { getOffering } from '../api/offerings';
import { CURRENT_TERM } from '../fixtures/offeringDetails';
import { useWorkspaceStore } from '../stores/workspaceStore';
import { ATTR_META, EXAM_WEIGHT_CHIP_HINT, REVIEW_TYPE_LABEL, type OfferingDetail } from '../types/domain';
import { formatCourseCode, formatMeetings } from '../utils/format';
import { Button } from './Button';
import { Chip } from './Chip';
import { EvaluationBar } from './EvaluationBar';
import styles from './OfferingDetailPanel.module.css';

export function OfferingDetailPanel() {
  const offeringId = useWorkspaceStore((s) => s.detailOfferingId);
  if (!offeringId) return null;
  // key remount로 offeringId 변경 시 inner state 초기화 (lint: set-state-in-effect 회피).
  return <OfferingDetailPanelInner key={offeringId} offeringId={offeringId} />;
}

function OfferingDetailPanelInner({ offeringId }: { offeringId: string }) {
  const close = useWorkspaceStore((s) => s.closeOfferingDetail);
  const openDetail = useWorkspaceStore((s) => s.openOfferingDetail);
  const [detail, setDetail] = useState<OfferingDetail | null>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') close();
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [close]);

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

  if (!detail) return null;

  return (
    <div className={styles.overlay} onClick={close}>
      <aside
        className={styles.panel}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <PanelHeader detail={detail} onClose={close} />
        <div className={styles.body}>
          <NoticeSection detail={detail} />
          <ProfileSection detail={detail} />
          <DetailsSection detail={detail} />
          <ReviewsSection detail={detail} />
          <LateralSection detail={detail} onOpen={openDetail} />
        </div>
      </aside>
    </div>
  );
}

function PanelHeader({ detail, onClose }: { detail: OfferingDetail; onClose: () => void }) {
  const wishlist = useWorkspaceStore((s) => s.wishlist);
  const addToWishlist = useWorkspaceStore((s) => s.addToWishlist);
  const removeFromWishlist = useWorkspaceStore((s) => s.removeFromWishlist);
  const openReviewModal = useWorkspaceStore((s) => s.openReviewModal);
  const inWishlist = wishlist.some((w) => w.id === detail.id);
  const room = detail.meetings.find((m) => m.room)?.room;

  return (
    <header className={styles.header}>
      <div className={styles.headerTopRow}>
        <div className={styles.chipsRow}>
          <Chip variant="soft">{detail.type}</Chip>
          <Chip>{detail.credit}학점</Chip>
          <Chip variant="soft">{detail.department}</Chip>
          {detail.englishOnly && <span className={styles.enBadge}>EN</span>}
          {detail.isOnline && <Chip variant="soft">온라인</Chip>}
          {detail.attributes.grading && (
            <Chip title={ATTR_META.grading.hint}>{ATTR_META.grading.label}·{detail.attributes.grading}</Chip>
          )}
          {detail.attributes.assignment && (
            <Chip title={ATTR_META.assignment.hint}>{ATTR_META.assignment.label}·{detail.attributes.assignment}</Chip>
          )}
          {detail.attributes.teamProject && (
            <Chip title={ATTR_META.teamProject.hint}>{ATTR_META.teamProject.label}·{detail.attributes.teamProject}</Chip>
          )}
          {detail.attributes.examWeight && (
            <Chip
              title={`${ATTR_META.examWeight.hint} (${EXAM_WEIGHT_CHIP_HINT[detail.attributes.examWeight] ?? ''})`}
            >
              {ATTR_META.examWeight.label}·{detail.attributes.examWeight}
            </Chip>
          )}
          {detail.attributes.attendance && (
            <Chip title={ATTR_META.attendance.hint}>{ATTR_META.attendance.label}·{detail.attributes.attendance}</Chip>
          )}
        </div>
        <button
          type="button"
          className={styles.closeBtn}
          onClick={onClose}
          aria-label="상세 닫기"
        >
          ×
        </button>
      </div>
      <div className={styles.courseName}>{detail.courseName}</div>
      <div className={styles.profLine}>
        {formatCourseCode(detail.id)} · {detail.professorName} · {CURRENT_TERM} · {formatMeetings(detail.meetings)}
        {room ? ` · ${room}` : ''}
      </div>
      <div className={styles.headerActions}>
        <Button
          variant={inWishlist ? 'default' : 'primary'}
          size="md"
          onClick={() => {
            if (inWishlist) {
              removeFromWishlist(detail.id);
            } else {
              addToWishlist({
                id: detail.id,
                courseName: detail.courseName,
                professorName: detail.professorName,
                credit: detail.credit,
                type: detail.type,
                meetings: detail.meetings,
              });
            }
          }}
        >
          {inWishlist ? '✓ Wishlist에서 제거' : '♡ Wishlist 담기'}
        </Button>
        <Button
          size="md"
          onClick={() => openReviewModal(detail.id)}
        >
          리뷰 작성
        </Button>
        {detail.syllabusUrl && (
          <a
            className={styles.syllabusLink}
            href={detail.syllabusUrl}
            target="_blank"
            rel="noopener noreferrer"
          >
            강의계획서 원문 ↗
          </a>
        )}
      </div>
    </header>
  );
}

function NoticeSection({ detail }: { detail: OfferingDetail }) {
  if (!detail.notice) return null;
  return (
    <div className={styles.section}>
      <div className={styles.sectionLabel}>특이사항</div>
      <div className={styles.noticeBody}>{detail.notice}</div>
    </div>
  );
}

function ProfileSection({ detail }: { detail: OfferingDetail }) {
  return (
    <div className={styles.section}>
      <div className={styles.sectionHead}>
        <div className={styles.sectionLabel}>요약 · AI 생성</div>
        <div className={styles.profileMeta}>
          리뷰 {detail.reviewCount}건 기반 · {detail.profileUpdatedAt} 갱신
        </div>
      </div>
      <div className={styles.profileGrid}>
        <div className={styles.profileKey}>주제</div>
        <div className={styles.profileVal}>{detail.profile.topic}</div>
        <div className={styles.profileKey}>수업 방식</div>
        <div className={styles.profileVal}>{detail.profile.format}</div>
        <div className={styles.profileKey}>평가</div>
        <div className={styles.profileVal}>{detail.profile.evaluation}</div>
        <div className={styles.profileKey}>리뷰 종합</div>
        <div className={styles.profileVal}>{detail.profile.reviewsSummary}</div>
        <div className={styles.profileKey}>주의</div>
        <div className={styles.profileVal}>{detail.profile.caveats}</div>
      </div>
    </div>
  );
}

function DetailsSection({ detail }: { detail: OfferingDetail }) {
  return (
    <div className={styles.section}>
      <div className={styles.sectionLabel}>평가 비중</div>
      <EvaluationBar items={detail.evaluation} />

      <div className={styles.sectionLabel} style={{ marginTop: 14 }}>
        주차별 주제
      </div>
      <div className={styles.weekList}>
        {detail.weeklyTopics.map((w) => (
          <div key={w.week} className={styles.weekItem}>
            <span className={styles.weekNum}>{w.week}주</span>
            <span>{w.topic}</span>
          </div>
        ))}
      </div>

      <div className={styles.sectionLabel} style={{ marginTop: 14 }}>
        선수과목
      </div>
      {detail.prerequisites.length === 0 ? (
        <div className={styles.empty}>없음</div>
      ) : (
        <div className={styles.prereqs}>
          {detail.prerequisites.map((p) => (
            <Chip key={p}>{p}</Chip>
          ))}
        </div>
      )}
    </div>
  );
}

function ReviewsSection({ detail }: { detail: OfferingDetail }) {
  const navigate = useNavigate();
  const close = useWorkspaceStore((s) => s.closeOfferingDetail);
  return (
    <div className={styles.section}>
      <div className={styles.sectionHead}>
        <div className={styles.sectionLabel}>대표 리뷰</div>
        <button
          type="button"
          className={styles.sectionLink}
          onClick={() => {
            close();
            navigate(`/offering/${detail.id}/reviews`);
          }}
        >
          전체 리뷰 보기 →
        </button>
      </div>
      <div className={styles.reviewList}>
        {detail.representativeReviews.map((r) => (
          <div key={r.id} className={styles.review}>
            <div className={styles.reviewMeta}>
              <span>#{r.rank}</span>
              {r.types.map((t) => (
                <span key={t} className={styles.reviewType}>
                  {REVIEW_TYPE_LABEL[t]}
                </span>
              ))}
              {r.term && <span>{r.term}</span>}
            </div>
            <div className={styles.reviewText}>{r.text}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function LateralSection({
  detail,
  onOpen,
}: {
  detail: OfferingDetail;
  onOpen: (id: string) => void;
}) {
  const navigate = useNavigate();
  const close = useWorkspaceStore((s) => s.closeOfferingDetail);
  const { sameCourse, sameProfessor } = detail.lateral;
  if (sameCourse.length === 0 && sameProfessor.length === 0) return null;
  return (
    <div className={styles.section}>
      <div className={styles.sectionHead}>
        <div className={styles.sectionLabel}>다른 학기·교수 / 이 교수 다른 과목</div>
        <button
          type="button"
          className={styles.sectionLink}
          onClick={() => {
            close();
            navigate(`/professor/${encodeURIComponent(detail.professorId)}`);
          }}
        >
          교수 프로필 →
        </button>
      </div>
      <div className={styles.lateralCols}>
        <div className={styles.lateralCol}>
          <div className={styles.lateralLabel}>같은 과목, 다른 학기/교수</div>
          {sameCourse.length === 0 ? (
            <div className={styles.empty}>다른 인스턴스 없음</div>
          ) : (
            sameCourse.map((s) => (
              <button
                key={s.id}
                type="button"
                className={styles.lateralItem}
                onClick={() => alert(`다른 학기 stub: ${s.term} ${s.professorName} (Tier 2 — Offering 인스턴스 데이터)`)}
              >
                <span>{s.professorName}</span>
                <span className={styles.lateralMeta}>{s.term}</span>
              </button>
            ))
          )}
        </div>
        <div className={styles.lateralCol}>
          <div className={styles.lateralLabel}>이 교수, 다른 과목</div>
          {sameProfessor.length === 0 ? (
            <div className={styles.empty}>다른 과목 없음</div>
          ) : (
            sameProfessor.map((s) => (
              <button
                key={s.id}
                type="button"
                className={styles.lateralItem}
                onClick={() => onOpen(s.id)}
              >
                <span>{s.courseName}</span>
                <span className={styles.lateralMeta}>{s.term}</span>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

