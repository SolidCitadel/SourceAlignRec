import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router';
import * as adminApi from '../api/admin';
import { Button } from '../components/Button';
import { PageHeader } from '../components/PageHeader';
import { SectionLabel } from '../components/SectionLabel';
import { TopBar } from '../components/TopBar';
import type { AdminPipelineStep } from '../types/domain';
import styles from './admin.module.css';

// 파이프라인 실행 트리거는 CLI 전용(별도 plan, api-contract/admin.md) — 실행 버튼 클릭 시에만 안내 노출.
const RUN_CLI_NOTICE = '파이프라인 실행은 CLI 전용입니다 (sar-* 명령)';

export function Admin() {
  const navigate = useNavigate();
  const [term, setTerm] = useState<string>('전체');
  const [runAllNotice, setRunAllNotice] = useState(false);

  const statsQuery = useQuery({
    queryKey: ['admin-stats', term],
    queryFn: () => adminApi.getStats(term),
  });
  const data = statsQuery.data ?? null;

  return (
    <div className={styles.shell}>
      <TopBar
        right={
          <select
            className={styles.termSelect}
            value={term}
            onChange={(e) => setTerm(e.target.value)}
          >
            {['전체', ...(data?.availableTerms ?? [])].map((t) => (
              <option key={t} value={t}>
                학기 · {t}
              </option>
            ))}
          </select>
        }
      />
      <PageHeader
        title="Admin 대시보드"
        sub="파이프라인 5단계 · operator 전용"
        onBack={() => navigate('/')}
      />
      <main className={styles.body}>
        {statsQuery.isLoading ? (
          <div className={styles.stateMsg}>불러오는 중…</div>
        ) : !data ? (
          <div className={styles.stateMsg}>통계를 불러오지 못했습니다.</div>
        ) : (
          <>
            <div className={styles.statsRow}>
              <section className={styles.card}>
                <SectionLabel>데이터 카운트</SectionLabel>
                <div className={styles.statGrid}>
                  <Stat label="수집학과" value={data.counts.departments} />
                  <Stat label="Course" value={data.counts.course} />
                  <Stat label="Offering" value={data.counts.offering} />
                  <Stat label="Review" value={data.counts.review} />
                </div>
              </section>
              <section className={styles.card}>
                <SectionLabel>Review 분류</SectionLabel>
                <div className={styles.statGrid}>
                  <Stat label="unprocessed" value={data.classification.unprocessed} tone="warn" />
                  <Stat label="valid" value={data.classification.valid} tone="ok" />
                  <Stat label="noise" value={data.classification.noise} tone="dim" />
                </div>
              </section>
            </div>

            <div className={styles.runAllRow}>
              {runAllNotice && <span className={styles.note}>{RUN_CLI_NOTICE}</span>}
              <Button
                variant="primary"
                onClick={() => {
                  setRunAllNotice(true);
                  window.setTimeout(() => setRunAllNotice(false), 2500);
                }}
              >
                전체 실행
              </Button>
            </div>

            <section className={styles.card}>
              <SectionLabel>파이프라인 단계별</SectionLabel>
              <div className={styles.pipelineTable}>
                <div className={[styles.pipelineRow, styles.pipelineHeadRow].join(' ')}>
                  <div>단계</div>
                  <div className={styles.numCol}>입력</div>
                  <div className={styles.numCol}>처리</div>
                  <div className={styles.numCol}>미처리</div>
                  <div className={styles.numCol}>마지막 실행</div>
                  <div className={styles.actionCol}>액션</div>
                </div>
                {data.pipeline.map((p) => (
                  <PipelineRow key={p.name} step={p} termSelected={term !== '전체'} />
                ))}
              </div>
            </section>

            <section className={styles.card}>
              <SectionLabel>최근 실행 로그</SectionLabel>
              {data.recentLogs.length === 0 ? (
                <div className={styles.empty}>실행 기록이 없습니다.</div>
              ) : (
                <ul className={styles.logList}>
                  {data.recentLogs.map((log, i) => (
                    <li key={`${log.timestamp}-${i}`} className={styles.logRow}>
                      <span className={styles.logTime}>{log.timestamp}</span>
                      <span className={styles.logTask}>{log.task}</span>
                      <span className={styles.logDuration}>{log.duration}</span>
                      <span className={log.status === 'ok' ? styles.logOk : styles.logFail}>
                        {log.status === 'ok' ? '✓' : '✗'}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: 'warn' | 'ok' | 'dim' }) {
  const cls = [
    styles.statValue,
    tone === 'warn' ? styles.statWarn : '',
    tone === 'ok' ? styles.statOk : '',
    tone === 'dim' ? styles.statDim : '',
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <div className={styles.statBlock}>
      <div className={styles.statLabel}>{label}</div>
      <div className={cls}>{value.toLocaleString()}</div>
    </div>
  );
}

function PipelineRow({ step, termSelected }: { step: AdminPipelineStep; termSelected: boolean }) {
  // 학기 무관 단계는 학기 선택 시에도 전체 카운트 유지 — '전체' 배지로 명시.
  const showAllBadge = termSelected && !step.termScoped;
  const [runNotice, setRunNotice] = useState(false);
  const onRun = () => {
    setRunNotice(true);
    window.setTimeout(() => setRunNotice(false), 2500);
  };
  return (
    <div className={styles.pipelineRow}>
      <div className={styles.stepName}>
        {step.name}
        {showAllBadge && <span className={styles.termBadge}>전체</span>}
      </div>
      <div className={styles.numCol}>{step.input.toLocaleString()}</div>
      <div className={styles.numCol}>{step.processed.toLocaleString()}</div>
      <div className={[styles.numCol, step.pending > 0 ? styles.pendingWarn : ''].filter(Boolean).join(' ')}>
        {step.pending}
      </div>
      <div className={[styles.numCol, styles.lastRun].join(' ')}>{step.lastRunAt}</div>
      <div className={styles.actionCol}>
        {runNotice ? (
          <span className={styles.runNotice} title={RUN_CLI_NOTICE}>
            CLI 전용
          </span>
        ) : (
          <Button size="sm" onClick={onRun}>
            실행
          </Button>
        )}
      </div>
    </div>
  );
}
