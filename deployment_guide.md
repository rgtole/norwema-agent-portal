# NORWEMA Portal Deployment & GitHub Guide

This guide details the step-by-step commands and procedures to host the codebase on GitHub and deploy the Streamlit application to Google Cloud Run with Google Cloud Firestore database integration.

---

## Part 1: Host Code on GitHub

### 1. Initialize Local Repository
Open terminal in your project directory (`norwema_agent_portal`) and run:
```bash
git init
```

### 2. Configure Git Exclusions
Create a `.gitignore` file to avoid pushing credentials, caches, or virtual environments:
```text
.venv/
__pycache__/
*.pyc
.streamlit/
*_db.json
.env
```

### 3. Commit Locally
```bash
git add .
git commit -m "Initial commit of NORWEMA Agent Portal with Firestore DB integration"
```

### 4. Create and Push to Remote GitHub Repository
1. Go to [GitHub](https://github.com/) and create a new repository named `norwema-agent-portal`. Leave description and README options blank.
2. Link your local repository and push:
```bash
git branch -M main
git remote add origin https://github.com/rgtole/norwema-agent-portal.git
git push -u origin main
```

---

## Part 2: Setup Google Cloud Platform (GCP)

### 1. Install Google Cloud SDK
Ensure you have the `gcloud` CLI installed. If not, follow instructions at [Install Cloud SDK](https://cloud.google.com/sdk/docs/install).

### 2. Log in and Select Project
```bash
# Log in to your GCP Account
gcloud auth login

# Set your active project ID (Replace with your actual project ID)
gcloud config set project YOUR_PROJECT_ID
```

### 3. Enable Required Services
Activate the Google APIs required for database and container hosting:
```bash
gcloud services enable \
    firestore.googleapis.com \
    artifactregistry.googleapis.com \
    run.googleapis.com \
    cloudbuild.googleapis.com
```

---

## Part 3: Configure Cloud Firestore

Firestore is a fully managed serverless NoSQL document database.

### 1. Create a Firestore Database
Create the database in Native Mode:
```bash
gcloud firestore databases create --location=europe-west2 --type=firestore-native
```
*(You can replace `europe-west2` with your preferred region, such as `us-central1`)*.

Once created:
*   The database is serverless and scales to zero (has a generous free tier of 50,000 read operations/day).
*   Collections (`events`, `blogs`, `registrations`, `form_schemas`) will be automatically created on first document write.

---

## Part 4: Dockerize & Push to Artifact Registry

### 1. Create Artifact Registry Repository
Create a repository named `norwema-repo` to store your Docker container image:
```bash
gcloud artifacts repositories create norwema-repo \
    --repository-format=docker \
    --location=europe-west2 \
    --description="Docker repository for NORWEMA Portal"
```

### 2. Configure Docker Authentication
Configure your local Docker daemon to authenticate with Google Artifact Registry:
```bash
gcloud auth configure-docker europe-west2-docker.pkg.dev
```

### 3. Build and Push the Image via Cloud Build
Instead of building locally and consuming upload bandwidth, you can submit the code directly to Google Cloud Build to compile the image:
```bash
gcloud builds submit --tag europe-west2-docker.pkg.dev/YOUR_PROJECT_ID/norwema-repo/norwema-app:latest
```

---

## Part 5: Deploy to Google Cloud Run

Google Cloud Run hosts your container and scales it automatically based on incoming web traffic.

### 1. Deploy the Container
Run the deployment command. We configure it to allow public, unauthenticated access so external users can access the homepage:
```bash
gcloud run deploy norwema-app \
    --image=europe-west2-docker.pkg.dev/YOUR_PROJECT_ID/norwema-repo/norwema-app:latest \
    --region=europe-west2 \
    --allow-unauthenticated \
    --port=8080
```

### 2. Grant Firestore Permissions to the Cloud Run Service Account
By default, Cloud Run uses the Compute Engine default service account. You must grant this service account permissions to read and write to Firestore:

```bash
# Find Compute Engine default service account email
SERVICE_ACCOUNT=$(gcloud iam service-accounts list --filter="displayName:Compute Engine default service account" --format="value(email)")

# Add Firestore User role to the service account
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/datastore.user"
```
*(Note: Firestore uses `roles/datastore.user` to manage read/write permissions)*.

### 3. Retrieve Your Portal URL
Once deployed successfully, Cloud Run outputs a URL resembling:
`https://norwema-app-xxxxxx-ew.a.run.app`

Open this link in any browser to access your live portal. All data entries (events, blog drafts, registration forms) will now persist securely inside Firestore!
