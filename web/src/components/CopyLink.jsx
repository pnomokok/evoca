import React, { useState } from 'react';
import { Check, Copy } from 'lucide-react';

// A personal link in a read-only field with a copy button. The link is a password:
// it is only shown, never logged or sent anywhere.
export default function CopyLink({ url, label = 'Personal link' }) {
  const [copied, setCopied] = useState(false);

  const copy = async (e) => {
    const field = e.currentTarget.parentElement.querySelector('input');
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      // No clipboard access (an insecure origin): select the text so it can be copied by hand.
      field?.select();
      if (!document.execCommand?.('copy')) return;
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="copy-link-row">
      <input
        className="archival-input-select copy-link-field"
        value={url}
        readOnly
        aria-label={label}
        onFocus={(e) => e.target.select()}
      />
      <button type="button" className="editorial-btn secondary" onClick={copy}>
        {copied ? <Check size={14} /> : <Copy size={14} />}
        <span>{copied ? 'Copied' : 'Copy'}</span>
      </button>
    </div>
  );
}
