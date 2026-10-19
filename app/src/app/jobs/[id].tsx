// /jobs/<id>: a link to a job (docs/API.md ids). Processing resumes polling it
// and moves on to the result; a finished job goes straight there.
import { Redirect, useLocalSearchParams } from 'expo-router';

export default function JobLink() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return <Redirect href={{ pathname: '/processing', params: { job: id } }} />;
}
