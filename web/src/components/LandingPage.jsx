import React from 'react';
import './LandingPage.css';
import {
  Play,
  HelpCircle,
  Coffee,
  Volume2,
  HeartHandshake,
  Globe,
  Sparkles,
  ShieldCheck,
  Lock,
  BookOpen,
  Users,
  MessageSquare
} from 'lucide-react';

function GithubIcon({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
      <path d="M9 18c-4.51 2-5-2-7-2" />
    </svg>
  );
}

// The product's front page. Every demo button (header, hero, closing CTA) opens the demo modal (onTryDemo);
// signed in, they are "Open your family" (onOpenFamily) instead.
export default function LandingPage({ isSignedIn, onTryDemo, onCreateFamily, onOpenFamily }) {
  const handleScroll = (id) => {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth' });
    }
  };

  return (
    <div className="landing-container">
      {/* --------------------------------------------------------------------
          Sticky In-Page Navigation Bar
          -------------------------------------------------------------------- */}
      <nav className="landing-subnav" aria-label="Page navigation">
        <div className="landing-subnav-inner">
          <button type="button" className="landing-brand" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })} aria-label="Evoca, back to the top">
            <span className="brand-monogram">E</span>
            <span className="brand-name">Evoca</span>
          </button>
          <div className="landing-nav-links">
            <button
              type="button"
              className="landing-nav-link"
              onClick={() => handleScroll('the-problem')}
              style={{ background: 'none', border: 'none', cursor: 'pointer' }}
            >
              The Problem
            </button>
            <button
              type="button"
              className="landing-nav-link"
              onClick={() => handleScroll('how-it-works')}
              style={{ background: 'none', border: 'none', cursor: 'pointer' }}
            >
              How It Works
            </button>
            <button
              type="button"
              className="landing-nav-link"
              onClick={() => handleScroll('a-day-with-evoca')}
              style={{ background: 'none', border: 'none', cursor: 'pointer' }}
            >
              Daily Rhythm
            </button>
            <button
              type="button"
              className="landing-nav-link"
              onClick={() => handleScroll('who-its-for')}
              style={{ background: 'none', border: 'none', cursor: 'pointer' }}
            >
              Who It's For
            </button>
            <button
              type="button"
              className="landing-nav-link"
              onClick={() => handleScroll('privacy-promise')}
              style={{ background: 'none', border: 'none', cursor: 'pointer' }}
            >
              Privacy &amp; Trust
            </button>
          </div>

          <div className="landing-nav-actions">
            {isSignedIn ? (
              <button type="button" className="landing-nav-cta" onClick={onOpenFamily}>
                <BookOpen size={14} />
                <span>Open your family</span>
              </button>
            ) : <>
              <button type="button" className="landing-nav-cta" onClick={onTryDemo}>
                <Play size={13} fill="currentColor" />
                <span>Try the demo</span>
              </button>
              <button type="button" className="landing-nav-cta secondary" onClick={onCreateFamily}>
                <Users size={14} />
                <span>Create your family</span>
              </button>
            </>}
          </div>
        </div>
      </nav>

      {/* --------------------------------------------------------------------
          1. HERO SECTION (Dark Atmospheric, Voice-First Living Memory)
          -------------------------------------------------------------------- */}
      <section className="landing-hero" id="hero">
        <div className="hero-bg-container">
          <img
            src="/images/grandmother_talking_kitchen_table.png"
            alt="Grandmother speaking warmly at a sunlit kitchen table"
            className="hero-bg-image"
          />
          <div className="hero-bg-overlay"></div>
        </div>
        <div className="hero-glow-blob"></div>

        <div className="landing-max-width hero-content">
          <div className="hero-waveform-badge">
            <svg
              viewBox="0 0 240 24"
              fill="none"
              className="hero-waveform-svg"
              strokeWidth="1.75"
              strokeLinecap="round"
              aria-hidden="true"
            >
              <path d="M0 12h50c4 0 6-6 10-6s6 12 10 12 6-16 10-16 6 20 10 20 6-14 10-14 6 8 10 8 6-4 10-4h120" />
            </svg>
            <span className="hero-badge-text">A Voice-First Living Memory</span>
          </div>

          <h1 className="hero-title">
            A voice-first family memory. Grandma just talks; the whole family listens, asks and remembers with her.
          </h1>

          <p className="hero-description">
            Evoca turns ordinary kitchen conversations into enduring family history. No touchscreens, no passwords, and no manual recordings—just an elder speaking naturally, while her family listens, asks thoughtful questions, and treasures her voice for generations.
          </p>

          <div className="hero-actions">
            {isSignedIn ? (
              <button type="button" className="btn-hero-primary" onClick={onOpenFamily}>
                <BookOpen size={16} />
                <span>Open your family</span>
              </button>
            ) : <>
              {/* The page's one large button; nothing else in the hero opens the demo. */}
              <div className="hero-cta-main">
                <button type="button" className="btn-hero-primary btn-hero-demo" onClick={onTryDemo}>
                  <Play size={18} fill="currentColor" />
                  <span>Try the demo</span>
                </button>
                <span className="hero-cta-note">No sign-up · about 3 minutes</span>
              </div>
              <button type="button" className="btn-hero-quiet" onClick={onCreateFamily}>
                <Users size={16} />
                <span>Create your family</span>
              </button>
            </>}
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------------------
          2. THE PROBLEM SECTION (The Living Conversation Gap)
          -------------------------------------------------------------------- */}
      <section className="landing-section landing-problem" id="the-problem">
        <div className="landing-max-width">
          <div className="problem-grid">
            <div className="problem-text-column">
              <span className="landing-badge terracotta">The Living Conversation Gap</span>
              <h2 className="landing-h2">
                Family stories shouldn’t end with whoever was sitting at the table.
              </h2>
              <p>
                In most homes, an elder’s richest memories only surface when someone happens to ask the right question on a Sunday afternoon. Those precious stories stay with whoever was sitting at the table, fading slowly as years pass.
              </p>
              <p>
                Existing memory books and recording kits turn life stories into homework. They demand questionnaires, typed memoirs, and one-way bound volumes that sit unread on a shelf. Evoca keeps memories alive as an ongoing, two-way conversation that brings the entire family together every single week.
              </p>
            </div>

            <div className="problem-image-column">
              <div className="problem-image-card">
                <img
                  src="/images/elder_hands_kitchen_table.webp"
                  alt="Candid close-up of grandmother's hands on a kitchen table"
                />
                <div className="problem-card-caption">
                  Kitchen conversations preserved with voice authenticity and natural rhythm.
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------------------
          3. HOW IT WORKS (The Conversation Loop)
          -------------------------------------------------------------------- */}
      <section className="landing-section landing-how" id="how-it-works">
        <div className="landing-max-width">
          <div className="how-layout">
            <div className="how-sticky-col">
              <span className="landing-badge sage">The Conversation Loop</span>
              <h2 className="landing-h2">
                How the memory loop stays alive every day
              </h2>
              <div className="how-loop-tagline">
                <span>question → conversation → her voice, reaction → next conversation</span>
              </div>
              <p className="landing-lead" style={{ fontSize: '15px', marginBottom: '28px' }}>
                A continuous, gentle cycle that weaves family curiosity directly into morning rituals without imposing technology.
              </p>
            </div>

            <div className="how-steps-stack">
              {/* Step 1 */}
              <div className="how-step-card">
                <div className="step-icon-bubble">
                  <HelpCircle size={24} />
                </div>
                <div className="step-card-body">
                  <div className="step-card-header">
                    <h3 className="step-card-title">1. Question</h3>
                    <span className="step-number-tag">STEP 01</span>
                  </div>
                  <p className="step-card-desc">
                    A grandchild leaves a question through the family panel about her grandmother’s first job or how she met grandfather.
                  </p>
                </div>
              </div>

              {/* Step 2 */}
              <div className="how-step-card">
                <div className="step-icon-bubble">
                  <Coffee size={24} />
                </div>
                <div className="step-card-body">
                  <div className="step-card-header">
                    <h3 className="step-card-title">2. Conversation</h3>
                    <span className="step-number-tag">STEP 02</span>
                  </div>
                  <p className="step-card-desc">
                    The companion gently weaves the question into natural morning conversation at the kitchen table, without screens or confusing menus.
                  </p>
                </div>
              </div>

              {/* Step 3 */}
              <div className="how-step-card">
                <div className="step-icon-bubble">
                  <Volume2 size={24} />
                </div>
                <div className="step-card-body">
                  <div className="step-card-header">
                    <h3 className="step-card-title">3. Her Voice &amp; Reaction</h3>
                    <span className="step-number-tag">STEP 03</span>
                  </div>
                  <p className="step-card-desc">
                    The family hears her spoken answer in her own authentic voice, leaves voice or text reactions, and sparks the next morning’s question.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------------------
          4. A DAY WITH EVOCA (Daily Rhythm Across Two Worlds)
          -------------------------------------------------------------------- */}
      <section className="landing-section landing-daily" id="a-day-with-evoca">
        <div className="landing-max-width">
          <div className="daily-header-center">
            <span className="landing-badge terracotta">Daily Rhythm</span>
            <h2 className="landing-h2">A day with Evoca, across two worlds</h2>
            <p className="landing-lead">
              Bridging the quiet pace of the elder’s living room with the busy rhythm of family members on the go.
            </p>
          </div>

          <div className="daily-worlds-grid">
            {/* World 1: For the elder */}
            <div className="world-card">
              <div className="world-card-top">
                <div className="world-header-group">
                  <div className="world-icon-circle">
                    <Volume2 size={18} />
                  </div>
                  <h3 className="world-title">For the elder</h3>
                </div>
                <span className="world-type-badge">Spoken voice</span>
              </div>

              <div className="world-image-box">
                <img
                  src="/images/elderly_woman_smiling_window.webp"
                  alt="Elder smiling warmly by her window"
                />
              </div>

              <div className="world-quotes-list">
                <div className="world-quote-item">
                  <div className="world-quote-text">“Elif has a question for you.”</div>
                  <div className="world-quote-sub">
                    Spoken softly by the companion while she makes morning coffee.
                  </div>
                </div>

                <div className="world-quote-item">
                  <div className="world-quote-text">“Play me what I told about the harbour”</div>
                  <div className="world-quote-sub">
                    Grandma listens back to her own words whenever she wants to reminisce.
                  </div>
                </div>
              </div>
            </div>

            {/* World 2: For the family */}
            <div className="world-card">
              <div className="world-card-top">
                <div className="world-header-group">
                  <div className="world-icon-circle" style={{ background: 'rgba(104, 119, 91, 0.14)', color: 'var(--accent-sage)' }}>
                    <MessageSquare size={18} />
                  </div>
                  <h3 className="world-title">For the family</h3>
                </div>
                <span className="world-type-badge">Family web panel</span>
              </div>

              <div className="world-image-box">
                <img
                  src="/images/family_member_listening_phone.webp"
                  alt="Family member listening to an audio message on her phone"
                />
              </div>

              <div className="world-quotes-list">
                <div className="world-quote-item" style={{ borderLeftColor: 'var(--accent-sage)' }}>
                  <div className="world-quote-text">“Maybe give her a call.”</div>
                  <div className="world-quote-sub">
                    A gentle nudge sent to family members when a story touches on home.
                  </div>
                </div>

                <div className="world-quote-item" style={{ borderLeftColor: 'var(--accent-sage)' }}>
                  <div className="world-quote-text">“Elif laughed at your story”</div>
                  <div className="world-quote-sub">
                    Letting Grandma hear how much her stories delight her granddaughter.
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------------------
          5. WHO IT'S FOR (Designed for Families)
          -------------------------------------------------------------------- */}
      <section className="landing-section landing-audience" id="who-its-for">
        <div className="landing-max-width">
          <div className="daily-header-center">
            <span className="landing-badge sage">Designed for Families</span>
            <h2 className="landing-h2">Made for real families, not tech early adopters</h2>
            <p className="landing-lead">
              Crafted with deep empathy for multigenerational living and genuine human connection.
            </p>
          </div>

          <div className="audience-grid">
            <div className="audience-card">
              <div className="audience-icon">
                <HeartHandshake size={24} />
              </div>
              <h3 className="audience-title">Elders who will never install an app</h3>
              <p className="audience-desc">
                No touchscreens to navigate, no passwords to forget, and no updates to approve. Grandma simply talks as if speaking with an old friend.
              </p>
            </div>

            <div className="audience-card">
              <div className="audience-icon">
                <Globe size={24} />
              </div>
              <h3 className="audience-title">Families spread across cities and countries</h3>
              <p className="audience-desc">
                Whether grandchildren live three streets over or three time zones away, everyone shares one living archive and hears her genuine voice.
              </p>
            </div>

            <div className="audience-card">
              <div className="audience-icon">
                <Sparkles size={24} />
              </div>
              <h3 className="audience-title">A reason to come back every day</h3>
              <p className="audience-desc">
                Instead of an intimidating one-time interview, Evoca creates small daily moments of connection that deepen family ties week after week.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------------------
          6. PRIVACY PROMISE (Architectural Privacy & Dignity)
          -------------------------------------------------------------------- */}
      <section className="landing-section landing-privacy" id="privacy-promise">
        <div className="landing-max-width">
          <div className="privacy-grid">
            <div className="privacy-left">
              <span className="landing-badge dark">Uncompromising Dignity</span>
              <h2 className="landing-h2">
                “Keep this between us” is honoured, always.
              </h2>
              <p className="landing-lead">
                An elder must feel complete freedom when reflecting on her life. When she says “keep this between us,” Evoca instantly excludes that reflection from the family panel and never publishes it. Private moments never leak, and sensitive memories stay strictly in her control.
              </p>
            </div>

            <div className="privacy-right">
              <div className="privacy-card-right">
                <div className="privacy-card-header">
                  <div className="privacy-card-tag">
                    <ShieldCheck size={16} />
                    <span>Backend Determinism</span>
                  </div>
                  <Lock size={18} color="var(--accent-terracotta)" />
                </div>
                <h3 className="privacy-card-title">Architectural Privacy</h3>
                <p className="privacy-card-desc">
                  Privacy is enforced by deterministic backend rules before any AI model summarizes a story. We never train public models on your family's personal memories.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------------------
          7. CALL TO ACTION (CTA)
          -------------------------------------------------------------------- */}
      <section className="landing-cta" id="call-to-action">
        <div className="landing-max-width">
          <div className="cta-banner">
            <div className="cta-ambient-glow"></div>
            <div className="cta-banner-content">
              <span className="landing-badge terracotta" style={{ background: 'rgba(255, 255, 255, 0.08)', color: '#FAF6ED' }}>
                Begin the Conversation
              </span>
              <h2 className="landing-h2">Hear her stories while she is here to tell them</h2>
              <p className="landing-lead">
                Start capturing the laughter, wisdom, and small daily reflections that define your family. Try the demo, or start keeping your own family's stories.
              </p>

              <div className="cta-buttons-group">
                {isSignedIn ? (
                  <button type="button" className="btn-hero-primary" onClick={onOpenFamily}>
                    <BookOpen size={16} />
                    <span>Open your family</span>
                  </button>
                ) : <>
                  <button type="button" className="btn-hero-primary" onClick={onTryDemo}>
                    <Play size={16} fill="currentColor" />
                    <span>Try the demo</span>
                  </button>
                  <button type="button" className="btn-hero-secondary" onClick={onCreateFamily}>
                    <Users size={16} />
                    <span>Create your family</span>
                  </button>
                </>}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------------------
          8. FOOTER
          -------------------------------------------------------------------- */}
      <footer className="landing-footer">
        <div className="landing-max-width">
          <div className="footer-top">
            <div className="footer-brand">
              <div className="footer-monogram">E</div>
              <div>
                <div className="footer-brand-name">Evoca</div>
                <div className="footer-tagline">A voice-first family companion for generations of shared memory.</div>
              </div>
            </div>

            <div className="footer-nav">
              <button
                type="button"
                onClick={() => handleScroll('the-problem')}
                style={{ background: 'none', border: 'none', color: '#B8B0A2', cursor: 'pointer' }}
              >
                The Problem
              </button>
              <button
                type="button"
                onClick={() => handleScroll('how-it-works')}
                style={{ background: 'none', border: 'none', color: '#B8B0A2', cursor: 'pointer' }}
              >
                How It Works
              </button>
              <button
                type="button"
                onClick={() => handleScroll('privacy-promise')}
                style={{ background: 'none', border: 'none', color: '#B8B0A2', cursor: 'pointer' }}
              >
                Privacy &amp; Trust
              </button>
            </div>
          </div>

          <div className="footer-bottom">
            <div>
              Released under the <strong style={{ color: '#FAF6ED' }}>MIT License</strong>.{' '}
              <a href="https://github.com/pnomokok/evoca" target="_blank" rel="noopener noreferrer" className="footer-github">
                <GithubIcon size={14} />
                <span>View on GitHub</span>
              </a>
            </div>
            <div>© 2026 Evoca. All rights reserved.</div>
          </div>
        </div>
      </footer>
    </div>
  );
}
