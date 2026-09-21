"use client";

import { useState } from "react";
import { formatTime, parseTime } from "@/lib/time";
import styles from "./TimeField.module.css";

interface Props {
  label: string;
  value: number;
  onCommit: (seconds: number) => void;
  onSetToPlayhead: () => void;
}

export function TimeField({ label, value, onCommit, onSetToPlayhead }: Props) {
  const [draft, setDraft] = useState<string | null>(null); // null while not editing

  const commit = () => {
    const seconds = draft === null ? null : parseTime(draft);
    if (seconds !== null) onCommit(seconds);
    setDraft(null);
  };

  return (
    <div className={styles.field}>
      <label>
        <span className={styles.label}>{label}</span>
        <input
          className={styles.input}
          value={draft ?? formatTime(value)}
          inputMode="decimal"
          spellCheck={false}
          onFocus={(e) => {
            setDraft(formatTime(value));
            e.currentTarget.select();
          }}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
        />
      </label>
      <button type="button" className="text-action" onClick={onSetToPlayhead}>
        Set to playhead
      </button>
    </div>
  );
}
