import { useState } from 'react';
import { useApp } from '../../context/useApp';
import { apiClient } from '../../api/client';
import { announceChange } from '../../utils/stageChannel';

export const QUESTION_PLACEHOLDER = 'For example: what were winter days like at home when you were a child?';

// Sends a question to the center person (POST /api/questions), for the Ask dialog and the
// first-question composer alike: the same validation, the same sensitive-topic message
// (shown as the backend words it; it never names the topic) and the same "saved" toast.
// send() resolves to true when the question was accepted.
export function useSendQuestion() {
  const { showToast, centerPersonId, circleData } = useApp();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [filterWarning, setFilterWarning] = useState(null);

  const centerFirst = circleData?.members?.find(m => m.role === 'center')?.name?.split(' ')[0] || '';

  const send = async (text, period = null) => {
    if (!text.trim()) return false;
    setIsSubmitting(true);
    setFilterWarning(null);
    const targetId = centerPersonId || circleData?.circle?.center_person_id;
    if (!targetId) {
      showToast("We couldn't find who to ask.", 'error');
      setIsSubmitting(false);
      return false;
    }
    try {
      const res = await apiClient.postQuestion(targetId, text.trim(), period || null);
      if (res.status === 'filtered') {
        setFilterWarning(res.message);
        return false;
      }
      announceChange('question');
      showToast(
        centerFirst ? `Your question is saved for ${centerFirst}'s next morning chat.` : 'Your question is saved for the next morning chat.',
        'info'
      );
      return true;
    } catch (err) {
      console.error(err);
      showToast("Your question couldn't be sent. Please try again.", 'error');
      return false;
    } finally {
      setIsSubmitting(false);
    }
  };

  return { send, isSubmitting, filterWarning, clearWarning: () => setFilterWarning(null), centerFirst };
}
