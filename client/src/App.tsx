import './index.css';
import { PersonaCard } from './components/PersonaCard';
import { QuestionForm } from './components/QuestionForm';
import { SourcesList } from './components/SourcesList';
import { SynthesisPanel } from './components/SynthesisPanel';
import { useAsk } from './hooks/useAsk';

export default function App() {
  const { state, ask, resetSession } = useAsk();

  const isInputDisabled =
    !state.sessionId || state.phase === 'streaming' || state.isLocked;

  return (
    <div>
      <header className="app-header">
        <h1 className="app-title">결정장애 치료 플랫폼</h1>
        <p className="app-subtitle">선택지를 좁혀 커밋시켜 드립니다.</p>
        {state.requestionCount > 0 && (
          <p className="session-count">질문 {state.requestionCount}회째</p>
        )}
      </header>

      {/* ── 잠금 패널 ── */}
      {state.isLocked && (
        <div className="locked-panel">
          <p className="locked-message">
            {state.lockedMessage ?? '세션이 잠겼다.'}
          </p>
          <p className="locked-hint">
            {state.cooldownSec > 0
              ? `${state.cooldownSec}초 후 자동 해제된다.`
              : '아래 버튼을 눌러 리셋하거나 새 세션을 시작해라.'}
          </p>
          <button className="reset-button" onClick={resetSession}>
            리셋하고 다시 시작
          </button>
        </div>
      )}

      {/* ── 질문 폼 ── */}
      <QuestionForm
        onSubmit={ask}
        disabled={isInputDisabled}
        isStreaming={state.phase === 'streaming'}
      />

      {/* ── 스트리밍 상태 배지 ── */}
      {state.phase === 'streaming' && (
        <span className="status-badge streaming">페르소나들이 싸우는 중…</span>
      )}

      {/* ── 범위 외 질문 ── */}
      {state.verdict === 'out_of_scope' && state.phase === 'done' && (
        <p className="out-of-scope">이건 제가 답할 질문이 아니에요.</p>
      )}

      {/* ── 오류 ── */}
      {state.error && (
        <p className="error-msg">오류: {state.error}</p>
      )}

      {/* ── 출처 ── */}
      {state.sources.length > 0 && (
        <SourcesList sources={state.sources} summary="" />
      )}

      {/* ── 종합 결론 (페르소나보다 위에 노출) ── */}
      {state.synthesis && (
        <SynthesisPanel
          conclusion={state.synthesis.conclusion}
          forced_pick={state.synthesis.forced_pick}
          key_reasons={state.synthesis.key_reasons}
        />
      )}

      {/* ── 페르소나 답변 카드 (접기/펼치기) ── */}
      {state.personaAnswers.length > 0 && (
        <div className="persona-grid">
          {state.personaAnswers.map((a) => (
            <PersonaCard
              key={a.order}
              name={a.persona_name}
              answer={a.answer}
              order={a.order}
            />
          ))}
        </div>
      )}
    </div>
  );
}
