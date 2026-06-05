import type { ScheduledCourse, Timetable, Weekday } from '../types/domain';
import styles from './ScheduleGrid.module.css';

const DAYS: { key: Weekday; label: string }[] = [
  { key: 'Mon', label: '월' },
  { key: 'Tue', label: '화' },
  { key: 'Wed', label: '수' },
  { key: 'Thu', label: '목' },
  { key: 'Fri', label: '금' },
];

// 기본 표시 구간 9–19시. 더 이르거나(9시 전) 늦은(19시 후) 강의가 담기면 그 시간까지 자동 확장.
const BASE_START_HOUR = 9;
const BASE_END_HOUR = 19;

function timeToMinutes(time: string): number {
  const [h, m] = time.split(':').map(Number);
  return h * 60 + m;
}

/** timetable의 모든 교시를 포괄하도록 표시 시간 구간(시 단위)을 계산. 비면 기본 9–19. */
function computeHourRange(timetable: Timetable): { start: number; end: number } {
  let start = BASE_START_HOUR;
  let end = BASE_END_HOUR;
  for (const c of timetable.courses) {
    for (const m of c.meetings) {
      const startHour = Math.floor(timeToMinutes(m.startTime) / 60);
      const endHour = Math.ceil(timeToMinutes(m.endTime) / 60);
      if (startHour < start) start = startHour;
      if (endHour > end) end = endHour;
    }
  }
  return { start, end };
}

const BLOCK_VARIANTS = ['ink', 'primary', 'muted'] as const;
type BlockVariant = (typeof BLOCK_VARIANTS)[number];

function variantOf(courseIndex: number): BlockVariant {
  return BLOCK_VARIANTS[courseIndex % BLOCK_VARIANTS.length];
}

interface ScheduleGridProps {
  timetable: Timetable;
  onRemoveCourse?: (courseId: string) => void;
}

export function ScheduleGrid({ timetable, onRemoveCourse }: ScheduleGridProps) {
  const totalCredit = timetable.courses.reduce((s, c) => s + c.credit, 0);
  const { start, end } = computeHourRange(timetable);
  const hours = Array.from({ length: end - start }, (_, i) => start + i);
  const gridStartMin = start * 60;
  const gridTotalMin = (end - start) * 60;
  // meetings 없는 강의(온라인·시간미정)는 그리드에 못 올림 → 하단 별도 영역에 표시·제거.
  const unplaced = timetable.courses.filter((c) => c.meetings.length === 0);
  return (
    <div className={styles.card}>
      <header className={styles.header}>
        <div className={styles.titleRow}>
          <h2 className={styles.title}>{timetable.name}</h2>
          <span className={styles.summary}>
            {timetable.courses.length}과목 · {totalCredit}학점
          </span>
        </div>
      </header>
      <div
        className={styles.grid}
        style={{ gridTemplateRows: `22px repeat(${hours.length}, minmax(0, 1fr))` }}
      >
        <div />
        {DAYS.map((d) => (
          <div key={d.key} className={styles.dayLabel}>
            {d.label}
          </div>
        ))}
        {hours.map((h) => (
          <Row key={h} hour={h} />
        ))}
        <div className={styles.blocks}>
          {timetable.courses.map((course, idx) =>
            course.meetings.map((m, mi) => (
              <Block
                key={`${course.id}-${mi}`}
                course={course}
                day={m.day}
                start={m.startTime}
                end={m.endTime}
                variant={variantOf(idx)}
                gridStartMin={gridStartMin}
                gridTotalMin={gridTotalMin}
                onRemove={onRemoveCourse ? () => onRemoveCourse(course.id) : undefined}
              />
            )),
          )}
        </div>
      </div>
      {unplaced.length > 0 && (
        <div className={styles.unplaced}>
          <div className={styles.unplacedLabel}>온라인 · 시간 미정</div>
          <div className={styles.unplacedList}>
            {unplaced.map((course) => (
              <div key={course.id} className={styles.unplacedItem}>
                <div className={styles.unplacedBody}>
                  <div className={styles.unplacedName}>{course.courseName}</div>
                  <div className={styles.unplacedSub}>
                    {course.professorName} · {course.isOnline ? '온라인' : '시간 미정'} · {course.credit}학점
                  </div>
                </div>
                {onRemoveCourse && (
                  <button
                    type="button"
                    className={styles.unplacedRemove}
                    onClick={() => onRemoveCourse(course.id)}
                    aria-label={`${course.courseName} 시간표에서 제거`}
                    title="시간표에서 제거"
                  >
                    ×
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ hour }: { hour: number }) {
  return (
    <>
      <div className={styles.hourLabel}>{hour}</div>
      {DAYS.map((d) => (
        <div key={d.key} className={styles.cell} />
      ))}
    </>
  );
}

interface BlockProps {
  course: ScheduledCourse;
  day: Weekday;
  start: string;
  end: string;
  variant: BlockVariant;
  gridStartMin: number;
  gridTotalMin: number;
  onRemove?: () => void;
}

function Block({
  course,
  day,
  start,
  end,
  variant,
  gridStartMin,
  gridTotalMin,
  onRemove,
}: BlockProps) {
  const dayIndex = DAYS.findIndex((d) => d.key === day);
  if (dayIndex < 0) return null;
  const topPct = ((timeToMinutes(start) - gridStartMin) / gridTotalMin) * 100;
  const heightPct = ((timeToMinutes(end) - timeToMinutes(start)) / gridTotalMin) * 100;
  const meetingRoom = course.meetings.find((m) => m.day === day && m.startTime === start)?.room;
  return (
    <div
      className={[styles.block, styles[`v-${variant}`]].join(' ')}
      style={{
        left: `calc(${dayIndex} * 20% + 2px)`,
        top: `${topPct}%`,
        height: `${heightPct}%`,
      }}
    >
      <div className={styles.blockTitle}>{course.courseName}</div>
      <div className={styles.blockSub}>
        {course.professorName}
        {meetingRoom ? ` · ${meetingRoom}` : ''}
      </div>
      <div className={styles.blockTag}>{course.type}</div>
      {onRemove && (
        <button
          type="button"
          className={styles.blockRemove}
          onClick={onRemove}
          aria-label={`${course.courseName} 시간표에서 제거`}
          title="시간표에서 제거"
        >
          ×
        </button>
      )}
    </div>
  );
}
