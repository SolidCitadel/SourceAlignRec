import styles from './WishlistRail.module.css';

interface WishlistRailProps {
  count: number;
  onExpand: () => void;
}

export function WishlistRail({ count, onExpand }: WishlistRailProps) {
  return (
    <button type="button" className={styles.rail} onClick={onExpand} aria-label="Wishlist 펼치기">
      <span className={styles.expand}>›</span>
      <span className={styles.label}>
        Wishlist <span className={styles.count}>· {count}</span>
      </span>
    </button>
  );
}
