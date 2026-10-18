import React, { useMemo, useState } from 'react';
import { apiClient } from '../api/client';
import Modal from './Modal';
import CopyLink from './CopyLink';
import { fullInviteUrl, markLinked } from '../utils/inviteLinks';
import { ArrowLeft, ArrowRight, Check, X } from 'lucide-react';

const BROWSER_TZ = (() => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Istanbul';
  } catch {
    return 'Europe/Istanbul';
  }
})();

const STEPS = [
  { title: 'Your family', fields: ['circle_name', 'chat_time', 'timezone'] },
  { title: 'The storyteller', fields: ['center.name', 'center.birth_year'] },
  { title: 'You', fields: ['creator.name', 'creator.birth_year', 'creator.relation_to_center'] },
];

const LABELS = {
  'circle_name': 'Family name',
  'chat_time': 'Morning chat time',
  'timezone': 'Time zone',
  'center.name': 'Name',
  'center.birth_year': 'Birth year',
  'creator.name': 'Your name',
  'creator.birth_year': 'Your birth year',
  'creator.relation_to_center': 'Your relation to them',
};

const PLACEHOLDERS = {
  'circle_name': 'The Demir Family',
  'center.name': 'Hasan Demir',
  'center.birth_year': '1944',
  'creator.name': 'Selin Demir',
  'creator.birth_year': '1975',
  'creator.relation_to_center': 'daughter, grandson, niece...',
};

// "center.birth_year must be a year between 1900 and 2026." -> field and "Must be a year between ..."
function fieldError(detail) {
  const match = /^([a-z_.]+) (.+)$/.exec(detail || '');
  if (!match || !(match[1] in LABELS)) return null;
  const text = match[2] === 'is required.' ? 'Please fill this in.' : match[2];
  return { field: match[1], message: text.charAt(0).toUpperCase() + text.slice(1) };
}

// "Create your family": POST /api/circles, then the creator's own link, then their family panel.
// It lives outside the app, so it stays open while the app restarts as the new family's admin.
export default function CreateFamilyWizard({ onClose, onCreated }) {
  const [step, setStep] = useState(0);
  const [values, setValues] = useState({
    'circle_name': '', 'chat_time': '10:00', 'timezone': BROWSER_TZ,
    'center.name': '', 'center.birth_year': '',
    'creator.name': '', 'creator.birth_year': '', 'creator.relation_to_center': '',
  });
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [link, setLink] = useState(null);

  const timezones = useMemo(() => {
    try {
      const all = Intl.supportedValuesOf?.('timeZone') || [];
      return all.includes(values.timezone) ? all : [values.timezone, ...all];
    } catch {
      return null;
    }
  }, [values.timezone]);

  const set = (field, value) => {
    setValues(v => ({ ...v, [field]: value }));
    setErrors(e => ({ ...e, [field]: null }));
    setFormError(null);
  };

  // Only "is it filled in" here; the server checks the rest and names the field.
  const missing = (fields) => fields.filter(f => !String(values[f]).trim());

  const next = (e) => {
    e.preventDefault();
    const empty = missing(STEPS[step].fields);
    if (empty.length) {
      setErrors(Object.fromEntries(empty.map(f => [f, 'Please fill this in.'])));
      return;
    }
    if (step < STEPS.length - 1) setStep(step + 1);
    else submit();
  };

  const submit = async () => {
    setBusy(true);
    setFormError(null);
    const year = v => (String(v).trim() === '' ? null : Number(v));
    try {
      const result = await apiClient.createCircle({
        circle_name: values.circle_name.trim(),
        timezone: values.timezone,
        chat_time: values.chat_time,
        center: { name: values['center.name'].trim(), birth_year: year(values['center.birth_year']) },
        creator: {
          name: values['creator.name'].trim(),
          birth_year: year(values['creator.birth_year']),
          relation_to_center: values['creator.relation_to_center'].trim(),
        },
      });
      apiClient.setSession({ session_token: result.session_token, person_id: result.creator_id, circle_id: result.circle_id });
      markLinked(result.circle_id, result.creator_id);
      setLink(fullInviteUrl(result.invite_url_path));
      onCreated();
    } catch (err) {
      const fe = err.status === 400 ? fieldError(err.message) : null;
      if (fe) {
        setErrors({ [fe.field]: fe.message });
        setStep(STEPS.findIndex(s => s.fields.includes(fe.field)));
      } else {
        setFormError(err.status === 400 ? err.message : "We couldn't create your family just now. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  };

  const field = (name, type = 'text') => (
    <div className="form-group" key={name}>
      <label className="form-label" htmlFor={`cf-${name}`}>{LABELS[name]}</label>
      {name === 'timezone' && timezones ? (
        <select id={`cf-${name}`} className="archival-input-select" value={values[name]} onChange={e => set(name, e.target.value)}>
          {timezones.map(tz => <option key={tz} value={tz}>{tz}</option>)}
        </select>
      ) : (
        <input
          id={`cf-${name}`}
          className="archival-input-select"
          type={type}
          inputMode={type === 'number' ? 'numeric' : undefined}
          value={values[name]}
          placeholder={PLACEHOLDERS[name]}
          onChange={e => set(name, e.target.value)}
          aria-invalid={Boolean(errors[name])}
          aria-describedby={errors[name] ? `cf-${name}-error` : undefined}
          maxLength={type === 'text' ? 60 : undefined}
        />
      )}
      {errors[name] && <p id={`cf-${name}-error`} className="field-error" role="alert">{errors[name]}</p>}
    </div>
  );

  if (link) {
    return (
      <Modal onClose={onClose} labelledBy="cf-done-title" closeOnBackdrop={false}>
        <div className="modal-title-row dialog-title-flex">
          <div>
            <h2 id="cf-done-title" className="archival-dialog-title">Your family is ready</h2>
            <p className="archival-dialog-sub">This is your personal link. It signs you in as yourself.</p>
          </div>
        </div>
        <CopyLink url={link} label="Your personal link" />
        <p className="section-desc" style={{ margin: '12px 0 0' }}>Save this link to open your family on another device.</p>
        <div className="dialog-action-bar">
          <button type="button" className="editorial-btn primary" onClick={onClose} autoFocus>
            <Check size={15} />
            <span>Open my family</span>
          </button>
        </div>
      </Modal>
    );
  }

  const isLast = step === STEPS.length - 1;
  return (
    <Modal onClose={() => !busy && onClose()} labelledBy="cf-title" closeOnBackdrop={false}>
      <div className="modal-title-row dialog-title-flex">
        <div>
          <h2 id="cf-title" className="archival-dialog-title">Create your family</h2>
          <p className="archival-dialog-sub">Step {step + 1} of {STEPS.length}: {STEPS[step].title}</p>
        </div>
        <button className="close-btn" onClick={onClose} aria-label="Close" disabled={busy}>
          <X size={20} />
        </button>
      </div>

      <form onSubmit={next} className="archival-form" noValidate>
        {step === 0 && <>
          {field('circle_name')}
          <p className="section-desc" style={{ margin: 0 }}>Each morning at this time the device in the storyteller's home lights up.</p>
          {field('chat_time', 'time')}
          {field('timezone')}
        </>}
        {step === 1 && <>
          <p className="section-desc" style={{ margin: 0 }}>The person whose stories the family keeps, who talks to Evoca at home.</p>
          {field('center.name')}
          {field('center.birth_year', 'number')}
        </>}
        {step === 2 && <>
          {field('creator.name')}
          {field('creator.birth_year', 'number')}
          {field('creator.relation_to_center')}
          <p className="section-desc" style={{ margin: 0 }}>You will be the family's admin: you can invite the others.</p>
        </>}

        {formError && <p className="field-error" role="alert">{formError}</p>}

        <div className="dialog-action-bar">
          {step > 0 && (
            <button type="button" className="editorial-btn secondary" onClick={() => setStep(step - 1)} disabled={busy}>
              <ArrowLeft size={15} />
              <span>Back</span>
            </button>
          )}
          <button type="submit" className="editorial-btn primary" disabled={busy}>
            <span>{isLast ? (busy ? 'Creating...' : 'Create family') : 'Next'}</span>
            {!isLast && <ArrowRight size={15} />}
          </button>
        </div>
      </form>
    </Modal>
  );
}
