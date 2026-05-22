interface Props {
  speaker?: string | null;
}

/// Small "You" / "Guest" pill showing who said the flagged claim. Guest is
/// amber (matches the transcript strip); host is sky. Renders nothing for
/// manual (Ask Glass) and anticipatory heads-up cards, which have no speaker.
export function SpeakerBadge({ speaker }: Props) {
  if (!speaker) return null;
  const isGuest = speaker === "Guest";
  return (
    <span
      className={
        "label-xs px-1.5 py-[1px] rounded border " +
        (isGuest
          ? "bg-amber-400/15 border-amber-400/25 text-amber-300"
          : "bg-sky-400/15 border-sky-400/25 text-sky-300")
      }
    >
      {speaker}
    </span>
  );
}
