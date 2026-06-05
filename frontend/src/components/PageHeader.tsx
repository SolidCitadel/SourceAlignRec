import styles from './PageHeader.module.css';

interface PageHeaderProps {
  title: string;
  back?: string;
  sub?: string;
  onBack?: () => void;
}

export function PageHeader({
  title,
  back = '← 작업공간',
  sub,
  onBack,
}: PageHeaderProps) {
  return (
    <div className={styles.header}>
      <button type="button" onClick={onBack} className={styles.back}>
        {back}
      </button>
      <h1 className={styles.title}>{title}</h1>
      {sub && <div className={styles.sub}>{sub}</div>}
    </div>
  );
}
