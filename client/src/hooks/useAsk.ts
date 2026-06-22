import { useCallback, useEffect, useReducer } from 'react';
import { streamSSE } from '../api/stream';
import type {
  DoneEvent,
  ErrorEvent,
  JudgeEvent,
  LockedEvent,
  PersonaAnswerEvent,
  Source,
  SourcesEvent,
  SynthesisEvent,
} from '../types/events';

// ── 상태 타입 ─────────────────────────────────────────────────

export interface PersonaAnswer {
  persona_name: string;
  answer: string;
  order: number;
}

export interface SynthesisData {
  conclusion: string;
  forced_pick: string;
  key_reasons: string[];
}

export type Phase = 'idle' | 'streaming' | 'done';

export interface AskState {
  sessionId: string | null;
  phase: Phase;
  isLocked: boolean;
  requestionCount: number;

  // SSE 결과
  verdict: 'subjective' | 'out_of_scope' | null;
  selectedPersonas: string[];
  isGrounded: boolean;
  sources: Source[];
  personaAnswers: PersonaAnswer[];
  synthesis: SynthesisData | null;

  // 한도 초과 (§10)
  lockedMessage: string | null;
  resetPath: string | null;
  cooldownSec: number;

  error: string | null;
}

const initialState: AskState = {
  sessionId: null,
  phase: 'idle',
  isLocked: false,
  requestionCount: 0,
  verdict: null,
  selectedPersonas: [],
  isGrounded: false,
  sources: [],
  personaAnswers: [],
  synthesis: null,
  lockedMessage: null,
  resetPath: null,
  cooldownSec: -1,
  error: null,
};

// ── 액션 ─────────────────────────────────────────────────────

type Action =
  | { type: 'SET_SESSION'; sessionId: string }
  | { type: 'START_STREAM' }
  | { type: 'HTTP_LOCKED' }
  | { type: 'EVT_JUDGE'; data: JudgeEvent }
  | { type: 'EVT_SOURCES'; data: SourcesEvent }
  | { type: 'EVT_PERSONA_ANSWER'; data: PersonaAnswerEvent }
  | { type: 'EVT_SYNTHESIS'; data: SynthesisEvent }
  | { type: 'EVT_DONE'; data: DoneEvent }
  | { type: 'EVT_LOCKED'; data: LockedEvent }
  | { type: 'EVT_ERROR'; data: ErrorEvent }
  | { type: 'SESSION_RESET' };

// ── Reducer ───────────────────────────────────────────────────

function reducer(state: AskState, action: Action): AskState {
  switch (action.type) {
    case 'SET_SESSION':
      return { ...state, sessionId: action.sessionId };

    case 'START_STREAM':
      return {
        ...state,
        phase: 'streaming',
        verdict: null,
        selectedPersonas: [],
        isGrounded: false,
        sources: [],
        personaAnswers: [],
        synthesis: null,
        lockedMessage: null,
        error: null,
      };

    case 'HTTP_LOCKED':
      return { ...state, phase: 'done', isLocked: true };

    case 'EVT_JUDGE':
      return {
        ...state,
        verdict: action.data.verdict,
        selectedPersonas: action.data.selected_personas,
        isGrounded: action.data.grounded,
      };

    case 'EVT_SOURCES':
      return { ...state, sources: action.data.sources };

    case 'EVT_PERSONA_ANSWER':
      return {
        ...state,
        personaAnswers: [...state.personaAnswers, action.data].sort(
          (a, b) => a.order - b.order,
        ),
      };

    case 'EVT_SYNTHESIS':
      return {
        ...state,
        synthesis: {
          conclusion: action.data.conclusion,
          forced_pick: action.data.forced_pick,
          key_reasons: action.data.key_reasons,
        },
      };

    case 'EVT_DONE':
      return {
        ...state,
        phase: 'done',
        requestionCount: action.data.requestion_count,
      };

    case 'EVT_LOCKED':
      return {
        ...state,
        phase: 'done',
        isLocked: true,
        lockedMessage: action.data.message,
        resetPath: action.data.reset_path,
        cooldownSec: action.data.cooldown_sec,
      };

    case 'EVT_ERROR':
      return { ...state, phase: 'done', error: action.data.message };

    case 'SESSION_RESET':
      return {
        ...state,
        isLocked: false,
        lockedMessage: null,
        resetPath: null,
        cooldownSec: -1,
        requestionCount: 0,
        phase: 'idle',
        error: null,
      };
  }
}

// ── Hook ─────────────────────────────────────────────────────

export function useAsk() {
  const [state, dispatch] = useReducer(reducer, initialState);

  // 세션 생성 (마운트 시 1회)
  useEffect(() => {
    fetch('/api/sessions', { method: 'POST' })
      .then((r) => r.json())
      .then(({ session_id }: { session_id: string }) =>
        dispatch({ type: 'SET_SESSION', sessionId: session_id }),
      )
      .catch(console.error);
  }, []);

  const ask = useCallback(
    async (question: string) => {
      if (!state.sessionId || state.phase === 'streaming') return;

      dispatch({ type: 'START_STREAM' });

      let res: Response;
      try {
        res = await fetch(`/api/sessions/${state.sessionId}/ask`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question }),
        });
      } catch (err) {
        dispatch({ type: 'EVT_ERROR', data: { message: String(err) } });
        return;
      }

      if (res.status === 423) {
        dispatch({ type: 'HTTP_LOCKED' });
        return;
      }

      if (!res.ok || !res.body) {
        dispatch({ type: 'EVT_ERROR', data: { message: `HTTP ${res.status}` } });
        return;
      }

      for await (const { event, data } of streamSSE(res)) {
        switch (event) {
          case 'judge':
            dispatch({ type: 'EVT_JUDGE', data: data as JudgeEvent });
            break;
          case 'sources':
            dispatch({ type: 'EVT_SOURCES', data: data as SourcesEvent });
            break;
          case 'persona_answer':
            dispatch({ type: 'EVT_PERSONA_ANSWER', data: data as PersonaAnswerEvent });
            break;
          case 'synthesis':
            dispatch({ type: 'EVT_SYNTHESIS', data: data as SynthesisEvent });
            break;
          case 'done':
            dispatch({ type: 'EVT_DONE', data: data as DoneEvent });
            break;
          case 'locked':
            dispatch({ type: 'EVT_LOCKED', data: data as LockedEvent });
            break;
          case 'error':
            dispatch({ type: 'EVT_ERROR', data: data as ErrorEvent });
            break;
        }
      }
    },
    [state.sessionId, state.phase],
  );

  const resetSession = useCallback(async () => {
    if (!state.sessionId) return;
    await fetch(`/api/sessions/${state.sessionId}/reset`, { method: 'POST' });
    dispatch({ type: 'SESSION_RESET' });
  }, [state.sessionId]);

  return { state, ask, resetSession };
}
