import { Navigate, Route, Routes } from "react-router-dom";
import LandingPage from "./pages/LandingPage";
import ApplyPage from "./pages/ApplyPage";
import AdminPage from "./pages/AdminPage";
import VerifyPage from "./pages/VerifyPage";
import TermsPage from "./pages/TermsPage";
import PolicyPage from "./pages/PolicyPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/about" element={<LandingPage section="about" />} />
      <Route path="/services" element={<LandingPage section="services" />} />
      <Route path="/contact" element={<LandingPage section="contact" />} />
      <Route path="/apply" element={<ApplyPage />} />
      <Route path="/admin" element={<AdminPage />} />
      <Route path="/verify/:uniqueId" element={<VerifyPage />} />
      <Route path="/terms" element={<TermsPage />} />
      <Route path="/policys" element={<PolicyPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
