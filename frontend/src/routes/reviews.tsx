import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router';
import * as offeringsApi from '../api/offerings';
import * as reviewsApi from '../api/reviews';
import { Button } from '../components/Button';
import { Chip } from '../components/Chip';
import { TopBar } from '../components/TopBar';
import { useWorkspaceStore } from '../stores/workspaceStore';
import {
  REVIEW_TYPE_LABEL,
  REVIEW_TYPE_ORDER,
  type ReviewClassificationType,
  type ReviewItem,
} from '../types/domain';
import styles from './reviews.module.css';

type SortKey = 'recent' | 'type';

export function Reviews() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const openReviewModal = useWorkspaceStore((s) => s.openReviewModal);

  const offeringQuery = useQuery({
    queryKey: ['offering', id],
    queryFn: () => offeringsApi.getOffering(id!),
    enabled: !!id,
  });
  const reviewsQuery = useQuery({
    queryKey: ['offering-reviews', id],
    queryFn: () => reviewsApi.list(id!),
    enabled: !!id,
  });
  const detail = offeringQuery.data ?? null;
  const reviews = reviewsQuery.data?.items ?? [];

  const [typeFilter, setTypeFilter] = useState<ReviewClassificationType[]>([]);
  const [termFilter, setTermFilter] = useState<string>('all');
  const [sort, setSort] = useState<SortKey>('recent');

  // 백엔드가 noise를 제외(valid + unprocessed)해 반환 (api-contract/reviews.md).
  // 타입 chip toggle 시 types 빈 리뷰는 자연 탈락(사용자 통제권).
  const visible = reviews;

  const terms = useMemo(() => {
    const set = new Set<string>();
    visible.forEach((r) => set.add(r.term));
    return Array.from(set).sort((a, b) => b.localeCompare(a));
  }, [visible]);

  const filtered = useMemo(() => {
    let list = visible;
    if (typeFilter.length) {
      list = list.filter((r) => r.types.some((t) => typeFilter.includes(t)));
    }
    if (termFilter !== 'all') {
      list = list.filter((r) => r.term === termFilter);
    }
    if (sort === 'recent') {
      list = [...list].sort((a, b) => b.term.localeCompare(a.term));
    } else {
      list = [...list].sort((a, b) => {
        const aLabel = a.types[0] ?? 'zz';
        const bLabel = b.types[0] ?? 'zz';
        return aLabel.localeCompare(bLabel);
      });
    }
    return list;
  }, [visible, typeFilter, termFilter, sort]);

  if (offeringQuery.isLoading) {
    return (
      <div className={styles.shell}>
        <TopBar />
        <div className={styles.notFound}>불러오는 중…</div>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className={styles.shell}>
        <TopBar />
        <div className={styles.notFound}>
          존재하지 않는 강의입니다.{' '}
          <Link to="/" className={styles.notFoundLink}>
            작업공간으로 돌아가기 →
          </Link>
        </div>
      </div>
    );
  }

  const toggleType = (t: ReviewClassificationType) => {
    setTypeFilter((cur) => (cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t]));
  };

  return (
    <div className={styles.shell}>
      <TopBar />

      <header className={styles.header}>
        <button type="button" className={styles.back} onClick={() => navigate(-1)}>
          ← {detail.courseName} · {detail.professorName}
        </button>
        <div className={styles.titleRow}>
          <h1 className={styles.title}>전체 리뷰</h1>
          <span className={styles.totalCount}>{visible.length}건</span>
          <div style={{ flex: 1 }} />
          <Button size="sm" variant="primary" onClick={() => openReviewModal(detail.id)}>
            리뷰 작성
          </Button>
        </div>
      </header>

      <div className={styles.filterBar}>
        <div className={styles.filterRow}>
          <div className={styles.filterLabel}>타입</div>
          <div className={styles.chipRow}>
            {REVIEW_TYPE_ORDER.map((t) => (
              <Chip
                key={t}
                variant={typeFilter.includes(t) ? 'active' : 'default'}
                onClick={() => toggleType(t)}
                style={{ cursor: 'pointer' }}
              >
                {REVIEW_TYPE_LABEL[t]}
              </Chip>
            ))}
          </div>
        </div>
        <div className={styles.filterRow}>
          <div className={styles.filterLabel}>학기</div>
          <select
            className={styles.select}
            value={termFilter}
            onChange={(e) => setTermFilter(e.target.value)}
          >
            <option value="all">전체</option>
            {terms.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <div className={styles.filterLabel} style={{ marginLeft: 18 }}>
            정렬
          </div>
          <select
            className={styles.select}
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
          >
            <option value="recent">최신순</option>
            <option value="type">타입순</option>
          </select>
          <div style={{ flex: 1 }} />
          <div className={styles.filteredCount}>
            {filtered.length === visible.length
              ? `${visible.length}건`
              : `${filtered.length}건 / 전체 ${visible.length}건`}
          </div>
        </div>
      </div>

      <main className={styles.list}>
        {filtered.length === 0 ? (
          <div className={styles.empty}>조건에 맞는 리뷰가 없습니다.</div>
        ) : (
          filtered.map((r) => <ReviewCard key={r.id} review={r} />)
        )}
      </main>
    </div>
  );
}

function ReviewCard({ review }: { review: ReviewItem }) {
  const hasNoTypes = review.types.length === 0;
  return (
    <article className={styles.card}>
      <div className={styles.cardText}>{review.text}</div>
      <div className={styles.cardMeta}>
        <span className={styles.cardTerm}>{review.term}</span>
        {review.types.map((t) => (
          <Chip key={t} variant="soft">
            {REVIEW_TYPE_LABEL[t]}
          </Chip>
        ))}
        {hasNoTypes && <Chip variant="soft">기타</Chip>}
      </div>
    </article>
  );
}
