import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router';
import * as professorsApi from '../api/professors';
import { Chip } from '../components/Chip';
import { SectionLabel } from '../components/SectionLabel';
import { TopBar } from '../components/TopBar';
import { useWorkspaceStore } from '../stores/workspaceStore';
import { REVIEW_TYPE_LABEL, type ProfessorDetail } from '../types/domain';
import styles from './professor.module.css';

export function Professor() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const openDetail = useWorkspaceStore((s) => s.openOfferingDetail);

  const profQuery = useQuery({
    queryKey: ['professor', id],
    queryFn: () => professorsApi.get(id!),
    enabled: !!id,
  });
  const prof = profQuery.data ?? null;

  if (profQuery.isLoading) {
    return (
      <div className={styles.shell}>
        <TopBar />
        <div className={styles.notFound}>불러오는 중…</div>
      </div>
    );
  }

  if (!prof) {
    return (
      <div className={styles.shell}>
        <TopBar />
        <div className={styles.notFound}>
          교수 정보를 찾을 수 없습니다.{' '}
          <Link to="/" className={styles.notFoundLink}>
            작업공간으로 →
          </Link>
        </div>
      </div>
    );
  }

  const openOfferingFromProf = (offeringId: string) => {
    openDetail(offeringId);
    navigate('/');
  };

  return (
    <div className={styles.shell}>
      <TopBar />

      <header className={styles.header}>
        <button type="button" className={styles.back} onClick={() => navigate(-1)}>
          ← 작업공간
        </button>
        <div className={styles.profileRow}>
          <div className={styles.avatar}>{prof.name[0]}</div>
          <div className={styles.profileBody}>
            <h1 className={styles.profileName}>{prof.name}</h1>
            <div className={styles.profileSub}>{prof.affiliation ?? '소속 정보 없음'}</div>
          </div>
        </div>
      </header>

      <main className={styles.body}>
        <ProfileSection prof={prof} />
        <ReviewsSection prof={prof} />
        <OfferingsSection prof={prof} onOpen={openOfferingFromProf} />
      </main>
    </div>
  );
}

function ProfileSection({ prof }: { prof: ProfessorDetail }) {
  const profile = prof.profile;
  return (
    <section className={styles.card}>
      <div className={styles.sectionHead}>
        <SectionLabel>요약 · AI 생성</SectionLabel>
        <div className={styles.sectionMeta}>리뷰 {prof.reviewCount}건 기반</div>
      </div>
      {profile ? (
        <div className={styles.kvGrid}>
          {[
            { key: '강의 운영', value: profile.format },
            { key: '평가 경향', value: profile.evaluation },
            { key: '학생 평 종합', value: profile.reviewsSummary },
            { key: '유의사항', value: profile.caveats },
          ].map((r) => (
            <div key={r.key} className={styles.kvRow}>
              <div className={styles.kvKey}>{r.key}</div>
              <div className={styles.kvValue}>{r.value}</div>
            </div>
          ))}
        </div>
      ) : (
        <div className={styles.empty}>교수 종합 프로필 준비 중입니다.</div>
      )}
    </section>
  );
}

function ReviewsSection({ prof }: { prof: ProfessorDetail }) {
  if (prof.representativeReviews.length === 0) return null;
  return (
    <section className={styles.card}>
      <SectionLabel>대표 리뷰</SectionLabel>
      <div className={styles.reviewList}>
        {prof.representativeReviews.map((r) => (
          <article key={r.id} className={styles.review}>
            <div className={styles.reviewText}>{r.text}</div>
            <div className={styles.reviewMeta}>
              <span className={styles.reviewRank}>#{r.rank}</span>
              <span className={styles.reviewTerm}>{r.term}</span>
              {r.types.map((t) => (
                <Chip key={t} variant="soft">
                  {REVIEW_TYPE_LABEL[t]}
                </Chip>
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function OfferingsSection({
  prof,
  onOpen,
}: {
  prof: ProfessorDetail;
  onOpen: (offeringId: string) => void;
}) {
  return (
    <section className={styles.card}>
      <SectionLabel>강의 목록</SectionLabel>
      {prof.offerings.length === 0 ? (
        <div className={styles.empty}>등록된 강의가 없습니다.</div>
      ) : (
        <ul className={styles.offeringList}>
          {prof.offerings.map((o) => (
            <li key={o.id}>
              <button
                type="button"
                className={styles.offeringRow}
                onClick={() => onOpen(o.id)}
              >
                <span className={styles.offeringName}>{o.courseName}</span>
                <Chip variant="soft">{o.type}</Chip>
                <span className={styles.offeringTerm}>{o.term}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
