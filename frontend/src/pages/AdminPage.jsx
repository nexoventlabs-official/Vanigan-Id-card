import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { approveMember, listMembers, rejectMember } from "../services/api";

export default function AdminPage() {
  const [adminKey, setAdminKey] = useState(localStorage.getItem("vanigan_admin_key") || "");
  const [members, setMembers] = useState([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const loadMembers = async () => {
    if (!adminKey) return;
    setLoading(true);
    setError("");
    try {
      const res = await listMembers(adminKey, status || undefined);
      setMembers(res.data.items || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Failed to load members");
      setMembers([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMembers();
  }, [status]);

  const saveKey = () => {
    localStorage.setItem("vanigan_admin_key", adminKey);
    loadMembers();
  };

  const updateStatus = async (uniqueId, action) => {
    try {
      if (action === "approve") await approveMember(adminKey, uniqueId);
      if (action === "reject") await rejectMember(adminKey, uniqueId);
      await loadMembers();
    } catch (e) {
      setError(e?.response?.data?.detail || "Status update failed");
    }
  };

  return (
    <div className="page admin-page">
      <header className="topbar">
        <div className="brand">Admin Panel</div>
        <nav>
          <Link to="/">Home</Link>
          <Link to="/apply">Apply</Link>
        </nav>
      </header>

      <section className="admin-auth">
        <input
          type="password"
          placeholder="Admin API Key"
          value={adminKey}
          onChange={(e) => setAdminKey(e.target.value)}
        />
        <button className="btn primary" onClick={saveKey}>
          Connect
        </button>
      </section>

      <section className="admin-filters">
        <button className={`btn ${status === "" ? "primary" : "ghost"}`} onClick={() => setStatus("")}>All</button>
        <button className={`btn ${status === "pending" ? "primary" : "ghost"}`} onClick={() => setStatus("pending")}>Pending</button>
        <button className={`btn ${status === "approved" ? "primary" : "ghost"}`} onClick={() => setStatus("approved")}>Approved</button>
        <button className={`btn ${status === "rejected" ? "primary" : "ghost"}`} onClick={() => setStatus("rejected")}>Rejected</button>
      </section>

      {loading && <p>Loading members...</p>}
      {error && <p className="error">{error}</p>}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Unique ID</th>
              <th>Name</th>
              <th>District</th>
              <th>Contact</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.unique_id}>
                <td>{m.unique_id}</td>
                <td>{m.name}</td>
                <td>{m.district}</td>
                <td>{m.contact_number}</td>
                <td>{m.status}</td>
                <td className="actions">
                  <button className="btn ghost" onClick={() => updateStatus(m.unique_id, "approve")}>Approve</button>
                  <button className="btn ghost" onClick={() => updateStatus(m.unique_id, "reject")}>Reject</button>
                  <a className="btn ghost" href={`http://localhost:8000/verify/${m.unique_id}`} target="_blank" rel="noreferrer">
                    Card
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
