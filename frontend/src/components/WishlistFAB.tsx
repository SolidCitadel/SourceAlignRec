import styles from './WishlistFAB.module.css';

interface WishlistFABProps {
  count: number;
  onClick: () => void;
}

export function WishlistFAB({ count, onClick }: WishlistFABProps) {
  return (
    <button type="button" className={styles.fab} onClick={onClick} aria-label="Wishlist 펼치기">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <path d="M3 5 L8 12 L13 5" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M5 3 L11 3" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
      </svg>
      Wishlist
      <span className={styles.count}>{count}</span>
    </button>
  );
}
