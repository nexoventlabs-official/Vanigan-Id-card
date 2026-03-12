import { useMemo } from "react";
import { useParams } from "react-router-dom";

export default function VerifyPage() {
  const { uniqueId } = useParams();
  const src = useMemo(() => `http://localhost:8000/verify/${uniqueId}`, [uniqueId]);

  return (
    <div className="page verify-page">
      <h2>Card Verification</h2>
      <p>This view loads the official ID card template from the backend.</p>
      <iframe title="ID Card" src={src} className="verify-frame" />
    </div>
  );
}
