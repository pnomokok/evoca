import React, { useState } from 'react';
import { Users, QrCode, Image as ImageIcon, Mic, Sparkles, Radio } from 'lucide-react';

export default function GatheringScreen() {
  const [activeQuestion, setActiveQuestion] = useState("Which year was this photograph taken in Akçaabat? Who remembers?");

  return (
    <div className="gathering-container">
      <div className="gathering-header">
        <span className="gathering-badge">
          <Users size={14} style={{ display: 'inline', marginRight: '4px' }} />
          Buluşma Modu · Family Gathering Session
        </span>
        <h1 style={{ fontSize: '32px', fontWeight: 800, color: '#fff' }}>
          Remembering Together Around the Living Room
        </h1>
        <p style={{ fontSize: '15px', color: 'var(--text-secondary)', maxWidth: '640px' }}>
          Grandma speaks with the Alexa device on the table, while family members scan the QR code to use their phones as synchronized microphones.
        </p>
      </div>

      <div className="gathering-main-grid">
        {/* QR Code Scan Card */}
        <div className="qr-box-card">
          <div style={{ width: '160px', height: '160px', background: '#f4f4f5', borderRadius: '12px', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '2px solid #e4e4e7' }}>
            {/* SVG QR Code Simulation */}
            <svg width="130" height="130" viewBox="0 0 100 100" fill="#18181b">
              <rect x="0" y="0" width="30" height="30" />
              <rect x="5" y="5" width="20" height="20" fill="#fff" />
              <rect x="10" y="10" width="10" height="10" />
              <rect x="70" y="0" width="30" height="30" />
              <rect x="75" y="5" width="20" height="20" fill="#fff" />
              <rect x="80" y="10" width="10" height="10" />
              <rect x="0" y="70" width="30" height="30" />
              <rect x="5" y="75" width="20" height="20" fill="#fff" />
              <rect x="10" y="80" width="10" height="10" />
              <rect x="40" y="10" width="10" height="10" />
              <rect x="40" y="30" width="20" height="10" />
              <rect x="10" y="40" width="10" height="20" />
              <rect x="30" y="50" width="15" height="15" />
              <rect x="60" y="40" width="10" height="10" />
              <rect x="50" y="70" width="20" height="10" />
              <rect x="80" y="60" width="10" height="20" />
            </svg>
          </div>
          <div>
            <div className="qr-title">Scan to Join as Microphone</div>
            <div className="qr-sub">Open your camera on your phone to connect instantly</div>
          </div>
        </div>

        {/* Gathering Photo & Memory Prompt */}
        <div className="gathering-prompt-card">
          <div className="photo-placeholder-box">
            <ImageIcon size={48} />
            <div style={{ fontWeight: 700, fontSize: '15px' }}>Old Family Photo · Summer in Akçaabat</div>
            <div style={{ fontSize: '12px', opacity: 0.8 }}>Archive ID: img_1968_garden</div>
          </div>

          <div>
            <div style={{ fontSize: '12px', color: 'var(--accent-gold)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              <Sparkles size={13} style={{ display: 'inline', marginRight: '4px' }} />
              Evoca Prompt
            </div>
            <div style={{ fontSize: '18px', fontWeight: 600, color: '#fff', marginTop: '4px' }}>
              "{activeQuestion}"
            </div>
          </div>

          <div>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '8px' }}>
              Active Participants in Room:
            </div>
            <div className="speakers-live-list">
              <div className="speaker-pill-live">
                <span className="speaker-live-dot" />
                <span>Fatma (Echo Show)</span>
              </div>
              <div className="speaker-pill-live">
                <span className="speaker-live-dot" />
                <span>Ayşe (Phone Mic)</span>
              </div>
              <div className="speaker-pill-live">
                <span className="speaker-live-dot" />
                <span>Elif (Phone Mic)</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
