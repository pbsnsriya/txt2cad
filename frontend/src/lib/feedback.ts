/** Feedback is written here, shown to the person exactly as it will go, and only leaves their computer if they open the link themselves. */

export const ISSUES_URL = 'https://github.com/pbsnsriya/txt2cad/issues/new';
const MAX_BODY = 5500;           // keeps the whole link under what browsers and GitHub accept

export interface FeedbackInput {
  rating: number;                // 1 to 5, 0 when not given
  comment: string;
  include: boolean;              // send the last request and what was built along with it
  prompt?: string;
  summary?: string;
  version?: number;
}

export interface Feedback { title: string; body: string; url: string }

export function buildFeedback(i: FeedbackInput): Feedback {
  const parts: string[] = [];
  parts.push(`**How useful was it?** ${i.rating ? `${i.rating} of 5` : 'not rated'}`);
  parts.push(`**What happened?**\n${i.comment.trim() || '(nothing written)'}`);
  if (i.include && (i.prompt || i.summary)) {
    parts.push('---\nIncluded because I ticked the box:');
    if (i.prompt) parts.push(`**What I asked**\n> ${i.prompt.trim().replace(/\n+/g, '\n> ')}`);
    if (i.summary) parts.push(`**What was built (version ${i.version ?? '?'})**\n${i.summary.trim()}`);
  }
  let body = parts.join('\n\n');
  if (body.length > MAX_BODY) body = `${body.slice(0, MAX_BODY - 20)}\n\n(cut to fit)`;
  const title = `Feedback${i.rating ? `: ${i.rating}/5` : ''}${i.comment.trim() ? ` - ${i.comment.trim().replace(/\s+/g, ' ').slice(0, 60)}` : ''}`;
  return { title, body, url: `${ISSUES_URL}?title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}` };
}
