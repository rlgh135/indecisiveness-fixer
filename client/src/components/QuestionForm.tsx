import { type KeyboardEvent, useState } from 'react';

interface Props {
  onSubmit: (question: string) => void;
  disabled: boolean;
  isStreaming: boolean;
}

export function QuestionForm({ onSubmit, disabled, isStreaming }: Props) {
  const [value, setValue] = useState('');

  const handleSubmit = () => {
    const q = value.trim();
    if (!q || disabled) return;
    onSubmit(q);
    setValue('');
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSubmit();
  };

  return (
    <div className="question-form">
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="결정하지 못한 것을 물어봐라. (Cmd+Enter로 제출)"
        disabled={disabled}
        rows={3}
      />
      <button onClick={handleSubmit} disabled={disabled || !value.trim()}>
        {isStreaming ? '생각 중…' : '물어보기'}
      </button>
    </div>
  );
}
