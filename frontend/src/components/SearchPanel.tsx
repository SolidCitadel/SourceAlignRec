import type { OfferingSearchResultView } from '../types/domain';
import { FilterSidebar } from './FilterSidebar';
import { ResultBoard } from './ResultBoard';
import styles from './SearchPanel.module.css';

interface SearchPanelProps {
  onCardClick: (result: OfferingSearchResultView) => void;
  onAIClick: () => void;
}

export function SearchPanel({ onCardClick, onAIClick }: SearchPanelProps) {
  return (
    <div className={styles.panel}>
      <FilterSidebar />
      <ResultBoard onCardClick={onCardClick} onAIClick={onAIClick} />
    </div>
  );
}
