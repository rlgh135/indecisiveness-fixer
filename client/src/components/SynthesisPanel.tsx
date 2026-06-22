interface Props {
  conclusion: string;
  forced_pick: string;
  key_reasons: string[];
}

export function SynthesisPanel({ conclusion, forced_pick, key_reasons }: Props) {
  return (
    <div className="synthesis">
      <h2 className="synthesis-title">결론</h2>
      <p className="synthesis-conclusion">{conclusion}</p>
      <div className="synthesis-pick">{forced_pick}</div>
      {key_reasons.length > 0 && (
        <ul className="synthesis-reasons">
          {key_reasons.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
