# Autonomous Enterprise Workflow AI 🤖

A robust, enterprise-grade multi-agent system designed to execute multi-step workflows with deep failure recovery, automated SLA monitoring, and complete auditability.

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=Streamlit&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)

## ✨ Core Features

1. **Meeting to Action Workflow**
   - Ingests meeting transcripts, logically extracts action items, and assigns owners entirely autonomously.
   - Dispatches contextual Email Summaries via Resend/SMTP to individual stakeholders.
2. **Employee Onboarding Hub**
   - Role-based task allocation fetching required items directly from Postgres databases.
   - Dynamic Buddy Assignment handling database availability.
   - Emits customized welcome and orientation emails without intervention.
3. **SLA Monitoring & Escalation System**
   - A background loop continuously searches for pending or blocked items.
   - Multi-step execution resilience triggers immediate **SLA Breach Alerts** to IT Support when unassigned/failing steps cross escalation thresholds.
4. **Live Audit Logging**
   - 100% auditable execution traces securely persisted to Supabase Backend and a localized `logs.json`.

---

## 🛠️ Technology Stack

- **Agents / Logic:** Python, CrewAI
- **Frontend / UI:** Streamlit
- **Database / Auth:** Supabase (PostgreSQL)
- **Email Providers:** Resend API & Native Python `smtplib`

---

## 🚀 Setup & Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/<your-username>/<repo-name>.git
   cd <repo-name>
   ```

2. **Install dependencies:**
   Ensure you are using Python 3.9+ or higher.
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**
   Create a `.env` file in the root directory. **CRITICAL: NEVER commit this file to Git or expose it publicly.**
   ```env
   # Database
   SUPABASE_URL=your_supabase_url
   SUPABASE_KEY=your_supabase_anon_key
   
   # Email Providers (Use Resend, SMTP, or Both)
   RESEND_API_KEY=your_resend_api_key
   SENDER_EMAIL=your_smtp_email
   EMAIL_PASSWORD=your_smtp_app_password
   ```

4. **Launch the application smoothly:**
   ```bash
   streamlit run app.py
   ```

---

## 🌐 Deployment Guide & Vercel Considerations

**IMPORTANT DEPLOYMENT NOTE:**  
Because this application relies on a complex Python state/backend (Streamlit & Background Agent Pipelines), **it cannot be hosted directly on Vercel as a fullstack application**. Vercel is designed for serverless functions and React/Next.js frontends, and struggles to natively host heavy, persistent Python websockets like Streamlit out of the box.

### 🏆 Recommended Deployment: Render or Railway
To host the *entire* application just as it looks locally with zero refactoring:
1. Push your repository to GitHub using the instructions below.
2. Link your GitHub account to a Python-native host like [Render](https://render.com) or [Railway](https://railway.app).
3. Create a **New Web Service**.
4. Set the Build Command: `pip install -r requirements.txt`.
5. Set the Start Command: `bash start.sh` (This automatically bootstraps Ollama, pulls `tinyllama`, and streams the backend).
6. Securely add your `.env` variables seamlessly inside the platform's **Environment Variables** dashboard interface.

### 🟡 Optional Component: Vercel Frontend Split
If you intend strictly to use **Vercel**, you are highly recommended to use Vercel *only* for the frontend. You would need to:
- Rewrite the `app.py` Streamlit UI into a static Next.js frontend.
- Convert your `agents.py` into FastAPI serverless routes hosted elsewhere.

---

## 🔒 Git Publishing Checklist

To push your local directory cleanly to GitHub without exposing your API keys, run these commands inside your project folder:

```bash
git init
git add .
git commit -m "Initial commit - Autonomous Workflow AI"
git branch -M main
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```
