'use client';

import { Modal } from '@/components/ui/modal';
import { PastBriefingsList } from '@/components/copilot/past-briefings-list';
import type { WeeklyBrief } from '@/lib/weekly-briefs';

type Props = {
  open: boolean;
  onClose: () => void;
  briefs: WeeklyBrief[];
  onSelect: (brief: WeeklyBrief) => void;
};

export function BriefingHistoryModal({ open, onClose, briefs, onSelect }: Props) {
  return (
    <Modal open={open} onClose={onClose} title="История брифингов" width={720}>
      <PastBriefingsList
        briefs={briefs}
        onSelect={(brief) => {
          onSelect(brief);
          onClose();
        }}
      />
    </Modal>
  );
}
