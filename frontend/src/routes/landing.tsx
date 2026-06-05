import { Link } from 'react-router';
import { Logo } from '../components/Logo';
import styles from './landing.module.css';

export function Landing() {
  return (
    <div className={styles.shell}>
      <LandingNav />

      <section className={styles.hero}>
        <div className={styles.heroLeft}>
          <span className={styles.betaPill}>● 경희대 컴퓨터공학과 베타</span>
          <h1 className={styles.heroTitle}>
            리뷰가 쌓일수록
            <br />
            <span className={styles.heroAccent}>똑똑해지는</span>
            <br />
            강의 허브
          </h1>
          <p className={styles.heroSub}>
            가입 학교 모든 강의를 한곳에. 본인이 남긴 리뷰가 곧 다음 사람의 추천이 됩니다.
            AI가 시간표 충돌까지 보고 추천해요.
          </p>
          <div className={styles.heroCta}>
            <Link to="/signup">
              <PillButton primary large>
                무료로 시작하기 →
              </PillButton>
            </Link>
            <span className={styles.heroCtaNote}>30초 가입 · 학교 이메일 불필요</span>
          </div>
        </div>
        <HeroArt />
      </section>

      <section className={styles.features}>
        <div className={styles.featuresLabel}>HOW IT WORKS</div>
        <h2 className={styles.featuresHead}>강의 정보 · 리뷰 · 시간표가 한 흐름</h2>
        <div className={styles.featuresGrid}>
          {FEATURES.map((f) => (
            <article key={f.num} className={styles.featureCard}>
              <div className={styles.featureIcon}>{f.icon}</div>
              <div className={styles.featureNum}>{f.num}</div>
              <h3 className={styles.featureTitle}>{f.title}</h3>
              <p className={styles.featureBody}>{f.body}</p>
            </article>
          ))}
        </div>
      </section>

      <footer className={styles.footer}>
        <span className={styles.footerCopy}>© 2026 CourseHub · 졸업 프로젝트</span>
        <div className={styles.footerLinks}>
          <span>이용약관</span>
          <span>개인정보</span>
          <span>피드백</span>
        </div>
      </footer>
    </div>
  );
}

function LandingNav() {
  return (
    <nav className={styles.nav}>
      <div className={styles.brand}>
        <Logo size={26} />
        <span className={styles.brandName}>CourseHub</span>
      </div>
      <div className={styles.navRight}>
        <Link className={styles.navLogin} to="/login">
          로그인
        </Link>
        <Link to="/signup">
          <PillButton primary>시작하기 →</PillButton>
        </Link>
      </div>
    </nav>
  );
}

function PillButton({
  children,
  primary,
  large,
}: {
  children: React.ReactNode;
  primary?: boolean;
  large?: boolean;
}) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: large ? '14px 22px' : '10px 18px',
        background: primary ? 'var(--color-primary)' : '#fff',
        color: primary ? '#fff' : 'var(--color-ink)',
        border: primary ? 'none' : '1.5px solid var(--color-ink)',
        borderRadius: 999,
        fontFamily: 'var(--font-body)',
        fontSize: large ? 16 : 14,
        fontWeight: 600,
        letterSpacing: '-0.01em',
        cursor: 'pointer',
        boxShadow: primary ? '0 6px 14px rgba(201, 100, 66, 0.25)' : 'none',
      }}
    >
      {children}
    </span>
  );
}

const FEATURES: { num: string; title: string; body: string; icon: React.ReactNode }[] = [
  {
    num: '01',
    title: '강의 + 리뷰가 한곳에',
    body: '학교의 모든 강의 정보. 본인이 들은 강의에 직접 리뷰 작성.',
    icon: <BookIcon />,
  },
  {
    num: '02',
    title: '강의 검색 및 AI 추천',
    body: '속성 필터링·검색으로 후보를 좁힌 다음, AI에게 추천과 설명을 들을 수 있어요.',
    icon: <ChatIcon />,
  },
  {
    num: '03',
    title: '시간표 계획',
    body: 'Wishlist에 담은 과목들로 시간 충돌 없는 여러 시안을 만들어보고 비교할 수 있어요.',
    icon: <SparklesIcon />,
  },
];

function BookIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
      <path
        d="M4 4h7v16H4z M13 4h7v16h-7z"
        stroke="var(--color-primary)"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path
        d="M7 8h2 M7 11h2 M16 8h2 M16 11h2"
        stroke="var(--color-primary)"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function ChatIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
      <path
        d="M4 6 H20 V16 H12 L8 20 V16 H4 Z"
        stroke="var(--color-primary)"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <circle cx="9" cy="11" r="1" fill="var(--color-primary)" />
      <circle cx="12" cy="11" r="1" fill="var(--color-primary)" />
      <circle cx="15" cy="11" r="1" fill="var(--color-primary)" />
    </svg>
  );
}

function SparklesIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
      <path
        d="M12 3 L13.5 9 L19 10.5 L13.5 12 L12 18 L10.5 12 L5 10.5 L10.5 9 Z"
        stroke="var(--color-primary)"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path
        d="M18 16 L18.7 18 L20.7 18.7 L18.7 19.3 L18 21 L17.3 19.3 L15.3 18.7 L17.3 18 Z"
        fill="var(--color-primary)"
      />
    </svg>
  );
}

function HeroArt() {
  return (
    <div className={styles.art}>
      <svg className={styles.artBg} viewBox="0 0 460 460" fill="none" aria-hidden="true">
        <circle cx="370" cy="100" r="80" fill="#f0a86b" opacity="0.22" />
        <circle cx="370" cy="100" r="48" fill="#f0a86b" opacity="0.35" />
        <g stroke="var(--color-primary)" strokeWidth="1.8" strokeLinecap="round">
          <path d="M 60 80 L 60 96" />
          <path d="M 52 88 L 68 88" />
          <path d="M 400 380 L 400 396" />
          <path d="M 392 388 L 408 388" />
        </g>
        <circle cx="120" cy="380" r="3.5" fill="var(--color-primary)" />
        <circle cx="420" cy="220" r="3" fill="var(--color-ink)" />
      </svg>

      {/* Card 1 — schedule mini (front) */}
      <div className={`${styles.artCard} ${styles.artCard1}`}>
        <div className={styles.artScheduleHeader}>
          <span className={styles.artScheduleTitle}>시안 1</span>
          <span className={styles.artScheduleMeta}>18학점</span>
        </div>
        <div className={styles.artGrid}>
          <div className={styles.artCol}>
            <div
              className={`${styles.artBlock} ${styles.artBlockInk}`}
              style={{ top: '20%', height: '20%' }}
            />
          </div>
          <div className={styles.artCol}>
            <div
              className={`${styles.artBlock} ${styles.artBlockPrimary}`}
              style={{ top: '50%', height: '24%' }}
            />
          </div>
          <div className={styles.artCol}>
            <div
              className={`${styles.artBlock} ${styles.artBlockInk}`}
              style={{ top: '20%', height: '20%' }}
            />
          </div>
          <div className={styles.artCol}>
            <div
              className={`${styles.artBlock} ${styles.artBlockPrimary}`}
              style={{ top: '50%', height: '24%' }}
            />
          </div>
          <div className={styles.artCol}>
            <div
              className={`${styles.artBlock} ${styles.artBlockSun}`}
              style={{ top: '10%', height: '14%' }}
            />
          </div>
        </div>
      </div>

      {/* Card 2 — AI chat (middle) */}
      <div className={`${styles.artCard} ${styles.artCard2}`}>
        <div className={styles.artAiLabel}>AI · 추천</div>
        <div className={styles.artAiUserRow}>
          <div className={styles.artAiAvatar} />
          <div className={styles.artAiUserBubble}>머신러닝 입문 추천해줘 — 과제 적은 거</div>
        </div>
        <div className={styles.artAiRec}>
          <div className={styles.artAiRecName}>#1 머신러닝 입문 · 김교수</div>
          <div className={styles.artAiRecMeta}>화·목 10:00 · 채점 너그러움 · 과제 적음</div>
        </div>
      </div>

      {/* Card 3 — review (back) */}
      <div className={`${styles.artCard} ${styles.artCard3}`}>
        <div className={styles.artChipRow}>
          <span className={`${styles.artChip} ${styles.artChipPrimary}`}>채점 너그러움</span>
          <span className={`${styles.artChip} ${styles.artChipNeutral}`}>과제 적음</span>
        </div>
        <div className={styles.artReviewBody}>
          "매주 실습은 있지만 분량은 가볍습니다. 채점은 관대한 편."
        </div>
        <div className={styles.artReviewMeta}>2025-1 · 객체지향프로그래밍</div>
      </div>
    </div>
  );
}
