/** Marker parser: "text[^1] more[^2]" → segments with citation indexes. */
export function parseAnswerMarkers(text: string): Array<
  | { type: "text"; value: string }
  | { type: "citation"; index: number }
> {
  const segments: Array<{ type: "text"; value: string } | { type: "citation"; index: number }> =
    [];
  const pattern = /\[\^(\d+)\]/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ type: "text", value: text.slice(lastIndex, match.index) });
    }
    segments.push({ type: "citation", index: Number(match[1]) });
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) {
    segments.push({ type: "text", value: text.slice(lastIndex) });
  }
  return segments;
}
