import { permanentRedirect } from 'next/navigation';

export default function TreatmentsRedirectPage() {
  permanentRedirect('/vet?tab=withdrawal');
}
