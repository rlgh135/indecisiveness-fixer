export interface JudgeEvent {
  verdict: 'subjective' | 'out_of_scope';
  selected_personas: string[];
  grounded: boolean;
}

export interface Source {
  title: string;
  url: string;
}

export interface SourcesEvent {
  sources: Source[];
  summary: string;
}

export interface PersonaAnswerEvent {
  persona_name: string;
  answer: string;
  order: number;
}

export interface SynthesisEvent {
  conclusion: string;
  forced_pick: string;
  key_reasons: string[];
}

export interface DoneEvent {
  requestion_count: number;
}

export interface LockedEvent {
  message: string;
  reset_path: string;
  cooldown_sec: number;
}

export interface ErrorEvent {
  message: string;
}
