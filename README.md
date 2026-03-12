# Vanigan ID Card MVP

Production-style MVP using React + FastAPI + MongoDB + Redis + Cloudinary + Docker.

## Stack
- Frontend: React (Vite)
- Backend: FastAPI
- Database: MongoDB
- Cache/OTP store: Redis
- Media: Cloudinary (optional, local fallback included)
- OTP SMS: Twilio Verify (optional, dev OTP fallback included)
- Containerization: Docker Compose

## Features
- Marketing landing page with dummy sections (About/Services/Contact)
- Apply flow on dedicated page (`/apply`)
- OTP verification before registration
- Form fields:
  - Upload Photo
  - Name
  - Membership
  - Assembly
  - District
  - DOB
  - Age
  - Blood Group
  - Address
  - Contact Number
- Unique member ID generation (`TVSM#########`)
- Admin panel (`/admin`) with approve/reject
- ID card verification page rendered from your template style
- QR code generated per member pointing to card verify URL

## Run with Docker
1. Ensure Docker Desktop is running.
2. From project root:
   ```bash
   docker compose up --build
   ```
3. Open:
   - Frontend: http://localhost:5173
   - Backend docs: http://localhost:8000/docs
   - Verify sample path format: http://localhost:8000/verify/<UNIQUE_ID>

## OTP behavior
- If Twilio credentials are configured in `backend/.env`, OTP is sent via SMS.
- If not configured, backend returns `dev_otp` for development testing.

## Admin access
- Set `ADMIN_API_KEY` in `backend/.env`
- Enter same key in `/admin` page.

## Cloudinary behavior
- If Cloudinary credentials are configured, photos upload to Cloudinary.
- Otherwise photos are stored locally under `backend/app/static/generated/photos`.
