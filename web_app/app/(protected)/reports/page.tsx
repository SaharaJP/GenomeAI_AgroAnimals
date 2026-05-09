import { redirect } from 'next/navigation';

export default function ReportsPageRedirect() {
  redirect('/analytics?tab=reports');
}
