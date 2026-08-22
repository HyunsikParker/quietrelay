export function RelayMark() {
  return (
    <svg className="relay-mark" viewBox="0 0 44 34" aria-hidden="true">
      <path d="M6 6 21 17 37 7M6 28l15-11 16 10" />
      <circle cx="6" cy="6" r="3.5" />
      <circle cx="6" cy="28" r="3.5" />
      <circle cx="21" cy="17" r="3.5" />
      <circle cx="37" cy="7" r="3.5" />
      <circle cx="37" cy="27" r="3.5" />
    </svg>
  );
}

export function Brand() {
  return (
    <div className="brand" aria-label="QuietRelay">
      <RelayMark />
      <span>QuietRelay</span>
    </div>
  );
}

