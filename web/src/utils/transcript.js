// The story page's transcript: timed words shown with the punctuation of their text.

const bare = (token) => token.replace(/’/g, "'").toLowerCase().replace(/[^\p{L}\p{N}_']/gu, '');

// The timed words may lack the punctuation and capitals of the segment's text ("garden" "Every"
// for "garden. Every"). Each word takes its token from the text when they match, so it reads
// "garden." and stays clickable; a token of punctuation alone ("—") sticks to the word before it.
export function punctuateWords(words, text) {
  const tokens = (text || '').split(/\s+/).filter(Boolean);
  let t = 0;
  return words.map(w => {
    const want = bare(w.w || '');
    // Look a few tokens ahead, so one odd token does not shift every word after it; the first
    // word may start anywhere (a story can begin mid-segment).
    const end = t === 0 ? tokens.length : Math.min(t + 4, tokens.length);
    for (let k = t; k < end; k += 1) {
      if (want && bare(tokens[k]) === want) {
        let display = tokens[k];
        t = k + 1;
        while (t < tokens.length && !bare(tokens[t])) display += ` ${tokens[t++]}`;
        return { ...w, display };
      }
    }
    return { ...w, display: w.w };
  });
}
