import { ProfileSurface } from '@/components/profiles/profile-surface';

export default async function ObjectProfilePage({ params }: { params: Promise<{ objectType: string; objectId: string }> }) {
  const { objectType, objectId } = await params;
  return <ProfileSurface objectType={objectType} objectId={objectId} />;
}
