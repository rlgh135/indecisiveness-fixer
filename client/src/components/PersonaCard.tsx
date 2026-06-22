import { useState } from 'react';

interface Props {
  name: string;
  answer: string;
  order: number;
}

export function PersonaCard({ name, answer, order }: Props) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="persona-card">
      <button
        className="persona-header"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <span className="persona-order">#{order}</span>
        <span className="persona-name">{name}</span>
        <span className="persona-toggle">{expanded ? '▲' : '▼'}</span>
      </button>
      {expanded && <p className="persona-answer">{answer}</p>}
    </div>
  );
}
