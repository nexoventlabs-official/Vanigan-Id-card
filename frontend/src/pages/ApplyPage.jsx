import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { requestOtp, submitApplication, verifyOtp } from "../services/api";

const initial = {
  name: "",
  membership: "",
  assembly: "",
  district: "",
  dob: "",
  age: "",
  blood_group: "",
  address: "",
  contact_number: "",
};

export default function ApplyPage() {
  const [form, setForm] = useState(initial);
  const [photo, setPhoto] = useState(null);
  const [otp, setOtp] = useState("");
  const [otpState, setOtpState] = useState({ requested: false, verified: false, devOtp: "" });
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const canSubmit = useMemo(() => otpState.verified && photo && !loading, [otpState.verified, photo, loading]);

  const onChange = (e) => setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));

  const onRequestOtp = async () => {
    setError("");
    try {
      const res = await requestOtp(form.contact_number);
      setOtpState({ requested: true, verified: false, devOtp: res.data.dev_otp || "" });
    } catch (e) {
      setError(e?.response?.data?.detail || "Unable to send OTP");
    }
  };

  const onVerifyOtp = async () => {
    setError("");
    try {
      await verifyOtp(form.contact_number, otp);
      setOtpState((prev) => ({ ...prev, verified: true }));
    } catch (e) {
      setError(e?.response?.data?.detail || "Invalid OTP");
    }
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!canSubmit) return;

    setLoading(true);
    setError("");
    setResult(null);

    try {
      const fd = new FormData();
      Object.entries(form).forEach(([key, value]) => fd.append(key, value));
      fd.append("photo", photo);

      const res = await submitApplication(fd);
      setResult(res.data);
      setForm(initial);
      setPhoto(null);
      setOtp("");
      setOtpState({ requested: false, verified: false, devOtp: "" });
    } catch (e) {
      setError(e?.response?.data?.detail || "Application submission failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page apply-page">
      <header className="topbar">
        <div className="brand">Vanigan ID Registration</div>
        <nav>
          <Link to="/">Home</Link>
          <Link to="/admin">Admin</Link>
        </nav>
      </header>

      <form className="apply-form" onSubmit={onSubmit}>
        <h2>Membership Application</h2>
        <p>Complete OTP verification before submitting your ID request.</p>

        <div className="form-grid">
          <input name="name" placeholder="Name" value={form.name} onChange={onChange} required />
          <input name="membership" placeholder="Membership" value={form.membership} onChange={onChange} required />
          <input name="assembly" placeholder="Assembly" value={form.assembly} onChange={onChange} required />
          <input name="district" placeholder="District" value={form.district} onChange={onChange} required />
          <input name="dob" type="date" placeholder="DOB" value={form.dob} onChange={onChange} required />
          <input name="age" type="number" placeholder="Age" value={form.age} onChange={onChange} required />
          <input name="blood_group" placeholder="Blood Group" value={form.blood_group} onChange={onChange} required />
          <input name="contact_number" placeholder="Contact Number (+91...)" value={form.contact_number} onChange={onChange} required />
          <textarea name="address" placeholder="Address" value={form.address} onChange={onChange} required />
          <input type="file" accept="image/png,image/jpeg,image/jpg,image/webp" onChange={(e) => setPhoto(e.target.files?.[0] || null)} required />
        </div>

        <div className="otp-row">
          <button type="button" className="btn ghost" onClick={onRequestOtp} disabled={!form.contact_number}>
            Request OTP
          </button>
          <input
            placeholder="Enter OTP"
            value={otp}
            onChange={(e) => setOtp(e.target.value)}
            disabled={!otpState.requested || otpState.verified}
          />
          <button type="button" className="btn ghost" onClick={onVerifyOtp} disabled={!otp || otpState.verified}>
            Verify OTP
          </button>
        </div>

        {otpState.devOtp && <p className="hint">Dev OTP: {otpState.devOtp} (visible only when SMS provider is not configured)</p>}
        {otpState.verified && <p className="success">Contact verified. You can now submit.</p>}
        {error && <p className="error">{error}</p>}

        <button className="btn primary" type="submit" disabled={!canSubmit}>
          {loading ? "Submitting..." : "Submit Application"}
        </button>
      </form>

      {result && (
        <section className="result-box">
          <h3>Application Submitted</h3>
          <p>
            Member ID: <strong>{result.unique_id}</strong>
          </p>
          <p>Status: {result.status}</p>
          <a className="btn ghost" href={`http://localhost:8000/verify/${result.unique_id}`} target="_blank" rel="noreferrer">
            Open ID Verification Page
          </a>
        </section>
      )}
    </div>
  );
}
