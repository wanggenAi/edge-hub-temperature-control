import { Navigate } from "react-router-dom";
import { useDevices } from "@/routes/use-data";

export function OverviewPage() {
  const { devices, loading, error } = useDevices();
  if (loading) return <p className="text-sm text-mute">Loading devices...</p>;
  if (error) return <p className="text-sm text-danger">{error}</p>;
  if (devices.length === 0) return <p className="text-sm text-mute">No devices available.</p>;
  return <Navigate to={`/devices/${devices[0].id}`} replace />;
}
