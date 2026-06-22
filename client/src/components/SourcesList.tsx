import { useState } from 'react';
import type { Source } from '../types/events';

interface Props {
  sources: Source[];
  summary: string;
}

export function SourcesList({ sources, summary }: Props) {
  const [expanded, setExpanded] = useState(false);

  if (sources.length === 0) return null;

  return (
    <div className="sources">
      <button className="sources-toggle" onClick={() => setExpanded((v) => !v)}>
        🔍 검색 근거 {sources.length}개 {expanded ? '▲' : '▼'}
      </button>
      {expanded && (
        <div className="sources-body">
          <p className="sources-summary">{summary}</p>
          <ul>
            {sources.map((s, i) => (
              <li key={i}>
                <a href={s.url} target="_blank" rel="noreferrer">
                  {s.title || s.url}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
