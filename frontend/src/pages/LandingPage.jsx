import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getLandingContent } from "../services/api";

const sections = {
  about: {
    title: "Our Mission",
    body: "We empower traders with a trusted identity layer and digital-first member services.",
  },
  services: {
    title: "Member Services",
    body: "ID issuance, QR verification, district-level administration, and secure records.",
  },
  contact: {
    title: "Contact Office",
    body: "Chennai HQ with district coordinators across Tamil Nadu.",
  },
};

export default function LandingPage({ section }) {
  const [content, setContent] = useState(null);

  useEffect(() => {
    getLandingContent()
      .then((res) => setContent(res.data))
      .catch(() => setContent(null));
  }, []);

  const panel = section ? sections[section] : null;

  return (
    <div className="page landing-page">
      <header className="topbar">
        <div className="brand">Vanigan Identity Portal</div>
        <nav>
          <Link to="/about">About</Link>
          <Link to="/services">Services</Link>
          <Link to="/contact">Contact</Link>
          <Link to="/admin">Admin</Link>
        </nav>
      </header>

      <section className="hero">
        <h1>{content?.heroTitle || "Tamilnadu Vanigargalin Sangamam"}</h1>
        <p>{content?.heroSubtitle || "Secure digital identity cards for every registered merchant."}</p>
        <div className="hero-actions">
          <Link className="btn primary" to="/apply">
            Apply For ID Card
          </Link>
          <a className="btn ghost" href="#highlights">
            Explore Portal
          </a>
        </div>
      </section>

      <section id="highlights" className="stats-grid">
        {(content?.stats || []).map((item) => (
          <div className="stat-card" key={item.label}>
            <h3>{item.value}</h3>
            <p>{item.label}</p>
          </div>
        ))}
      </section>

      <section className="info-cards">
        <article>
          <h3>District-level Governance</h3>
          <p>Each member profile captures district and assembly details for precise representation.</p>
        </article>
        <article>
          <h3>Secure Onboarding</h3>
          <p>OTP-based contact verification and admin approval keep registrations authentic.</p>
        </article>
        <article>
          <h3>QR-Powered Validation</h3>
          <p>Every card includes a QR code that opens the verification view in real time.</p>
        </article>
      </section>

      {panel && (
        <section className="section-panel">
          <h2>{panel.title}</h2>
          <p>{panel.body}</p>
        </section>
      )}
    </div>
  );
}
