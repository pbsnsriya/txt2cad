/** Things a request names that txt2cad cannot build yet, found while the person is still typing. The list comes from the server (GET /api/capabilities). */

export function findUnsupported(text: string, words: Record<string, string>): string[] {
  const found: { at: number; label: string }[] = [];
  const longestFirst = Object.entries(words).sort((a, b) => b[0].length - a[0].length);
  for (const [word, label] of longestFirst) {
    const m = new RegExp(`\\b${word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}s?\\b`, 'i').exec(text);
    if (m && !found.some((f) => f.label === label)) found.push({ at: m.index, label });
  }
  return found.sort((a, b) => a.at - b.at).map((f) => f.label);
}
