import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1",
});

export const requestOtp = (contact_number) => api.post("/auth/request-otp", { contact_number });
export const verifyOtp = (contact_number, otp) => api.post("/auth/verify-otp", { contact_number, otp });
export const submitApplication = (formData) => api.post("/public/apply", formData, { headers: { "Content-Type": "multipart/form-data" } });
export const getLandingContent = () => api.get("/public/landing-content");
export const listMembers = (adminKey, status) =>
  api.get("/admin/members", {
    headers: { "X-Admin-Key": adminKey },
    params: status ? { status } : {},
  });
export const approveMember = (adminKey, uniqueId) =>
  api.post(`/admin/members/${uniqueId}/approve`, {}, { headers: { "X-Admin-Key": adminKey } });
export const rejectMember = (adminKey, uniqueId) =>
  api.post(`/admin/members/${uniqueId}/reject`, {}, { headers: { "X-Admin-Key": adminKey } });

export default api;
