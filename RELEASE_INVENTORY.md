# CareerNova AI — Release Inventory (2026-11-26)

Branch `careernova/dashboard-redesign`, HEAD `46e3bb3`, stash `stash@{0}` (local only, never pushed). Generated read-only; nothing was staged, committed or pushed.

Legend: **A** new file · **M** modified · **D** deleted. Section 1 is already staged; sections 2 and 3 must be staged before committing (commands at the end).

## 1. Already staged (300 files)

```
M  .env.example
A  CAREERNOVA_DEMO_GUIDE.md
A  CAREERNOVA_HR_ASSIGNMENT_REPORT.md
A  CAREERNOVA_IMPLEMENTATION_REPORT.md
A  CAREERNOVA_TEST_REPORT.md
A  CAREERNOVA_TRANSFORMATION_REPORT.md
A  DATABASE_MIGRATION_GUIDE.md
A  DEPLOYMENT_AND_HANDOVER_GUIDE.md
A  FINAL_BLOCKER_CHECKLIST.md
A  FINAL_DATABASE_MIGRATION_CHECKLIST.md
A  FINAL_QA_REPORT.md
A  P2_IMPLEMENTATION_REPORT.md
A  P3_IMPLEMENTATION_REPORT.md
A  PROJECT_COMPLETION_STATUS.md
M  README.md
A  SMTP_SETUP.md
A  SUPER_ADMIN_SETUP.md
A  backend/data/career_tracks.json
A  backend/data/hr_question_guide.json
A  backend/data/product_docs/01_overview.md
A  backend/data/product_docs/02_workflow.md
A  backend/data/product_docs/03_resume_upload.md
A  backend/data/product_docs/04_internship_matching.md
A  backend/data/product_docs/05_cover_letters.md
A  backend/data/product_docs/06_interview_preparation.md
A  backend/data/product_docs/07_applications_and_assistant.md
M  backend/main.py
M  backend/manage.py
M  backend/models.py
M  backend/routes/admin.py
M  backend/routes/assistant.py
M  backend/routes/auth.py
A  backend/routes/career_tracks.py
M  backend/routes/internships.py
M  backend/routes/interviews.py
M  backend/routes/matches.py
A  backend/routes/prep.py
M  backend/routes/profiles.py
M  backend/routes/resumes.py
M  backend/routes/skill_gaps.py
A  backend/routes/study_documents.py
M  backend/schemas/assistant_schema.py
M  backend/schemas/internship_schema.py
M  backend/schemas/interview_schema.py
M  backend/schemas/match_schema.py
M  backend/schemas/profile_schema.py
M  backend/schemas/resume_schema.py
M  backend/schemas/user_schema.py
A  backend/services/assistant/doc_agent.py
M  backend/services/assistant/facts.py
A  backend/services/assistant/prep_agent.py
A  backend/services/assistant/product_help.py
M  backend/services/assistant/service.py
M  backend/services/assistant/tools.py
A  backend/services/audit.py
A  backend/services/avatars.py
A  backend/services/career_tracks.py
M  backend/services/cover_letter.py
M  backend/services/document_common.py
M  backend/services/email_service.py
M  backend/services/embeddings.py
M  backend/services/internship_seed.py
M  backend/services/interview_generator.py
M  backend/services/interview_service.py
A  backend/services/invitations.py
A  backend/services/job_insights.py
A  backend/services/job_sources.py
M  backend/services/llm/base.py
A  backend/services/llm/ollama_provider.py
A  backend/services/login_throttle.py
A  backend/services/mailer.py
M  backend/services/matching_agent.py
A  backend/services/prep/__init__.py
A  backend/services/prep/context.py
A  backend/services/prep/guidance.py
A  backend/services/prep/internships.py
A  backend/services/prep/questions.py
A  backend/services/prep/roadmap.py
A  backend/services/prep/roles.py
A  backend/services/product_kb.py
A  backend/services/resume_compare.py
A  backend/services/resume_insights.py
M  backend/services/resume_parser.py
A  backend/services/resume_readiness.py
A  backend/services/skill_progress.py
A  backend/services/study_documents.py
A  backend/services/study_qa.py
M  backend/services/vector_index.py
M  backend/utils/dependencies.py
M  backend/utils/roles.py
A  docs/assignment/evaluation/STUDY_RAG_EVAL.md
A  docs/assignment/evaluation/study_rag_results.json
A  evaluation/study_rag_eval.py
A  frontend/DEMO_GUIDE.md
M  frontend/README.md
M  frontend/index.html
M  frontend/package-lock.json
M  frontend/package.json
A  frontend/public/favicon.svg
M  frontend/src/App.test.jsx
A  frontend/src/api/admin.js
A  frontend/src/api/applications.js
A  frontend/src/api/assistant.js
M  frontend/src/api/auth.js
A  frontend/src/api/careerTracks.js
A  frontend/src/api/dashboard.js
A  frontend/src/api/documents.js
A  frontend/src/api/internships.js
A  frontend/src/api/interviews.js
A  frontend/src/api/matches.js
A  frontend/src/api/prep.js
A  frontend/src/api/profile.js
A  frontend/src/api/resumes.js
A  frontend/src/api/skillGaps.js
A  frontend/src/api/studyDocuments.js
A  frontend/src/components/brand/BrandMark.jsx
A  frontend/src/components/ui/Avatar.jsx
M  frontend/src/components/ui/Badge.jsx
M  frontend/src/components/ui/Button.jsx
M  frontend/src/components/ui/Card.jsx
A  frontend/src/components/ui/Checkbox.jsx
M  frontend/src/components/ui/EmptyState.jsx
M  frontend/src/components/ui/ErrorAlert.jsx
A  frontend/src/components/ui/Icon.jsx
M  frontend/src/components/ui/Input.jsx
M  frontend/src/components/ui/Modal.jsx
M  frontend/src/components/ui/Select.jsx
M  frontend/src/components/ui/Spinner.jsx
A  frontend/src/config/brand.js
M  frontend/src/context/AuthContext.jsx
A  frontend/src/context/AvatarContext.jsx
M  frontend/src/context/ToastContext.jsx
A  frontend/src/features/admin/AdminAuditPage.jsx
A  frontend/src/features/admin/AdminIndexPage.jsx
A  frontend/src/features/admin/AdminInternshipFormPage.jsx
A  frontend/src/features/admin/AdminInternshipsPage.jsx
A  frontend/src/features/admin/AdminOverviewPage.jsx
A  frontend/src/features/admin/AdminUsersPage.jsx
A  frontend/src/features/admin/admin.test.jsx
A  frontend/src/features/admin/adminShared.jsx
A  frontend/src/features/applications/ApplicationDetailPage.jsx
A  frontend/src/features/applications/ApplicationsPage.jsx
A  frontend/src/features/applications/applicationFormat.js
A  frontend/src/features/applications/applications.test.jsx
A  frontend/src/features/applications/components/ApplicationList.jsx
A  frontend/src/features/applications/components/ApplicationReminders.jsx
A  frontend/src/features/applications/components/ApplicationSummary.jsx
A  frontend/src/features/applications/components/DetailsEditor.jsx
A  frontend/src/features/applications/components/HistoryTimeline.jsx
A  frontend/src/features/applications/components/InterviewRounds.jsx
A  frontend/src/features/applications/components/NewApplicationForm.jsx
A  frontend/src/features/applications/components/ReminderItem.jsx
A  frontend/src/features/applications/components/RemindersPanel.jsx
A  frontend/src/features/applications/components/SavedInternships.jsx
A  frontend/src/features/applications/components/StatusControl.jsx
A  frontend/src/features/applications/components/TrashPanel.jsx
A  frontend/src/features/assistant/AssistantPage.jsx
A  frontend/src/features/assistant/assistant.test.jsx
A  frontend/src/features/assistant/assistantFormat.js
A  frontend/src/features/assistant/components/AssistantSwitch.jsx
A  frontend/src/features/assistant/components/Composer.jsx
A  frontend/src/features/assistant/components/ConversationList.jsx
A  frontend/src/features/assistant/components/MessageBubble.jsx
A  frontend/src/features/assistant/components/PrepActions.jsx
A  frontend/src/features/assistant/components/RichText.jsx
A  frontend/src/features/assistant/components/StudyDocumentPanel.jsx
A  frontend/src/features/assistant/prepAgent.test.jsx
A  frontend/src/features/auth/AcceptInvitationPage.jsx
A  frontend/src/features/auth/ForgotPasswordPage.jsx
A  frontend/src/features/auth/LoginPage.jsx
D  frontend/src/features/auth/LoginPlaceholderPage.jsx
A  frontend/src/features/auth/RegisterPage.jsx
A  frontend/src/features/auth/ResetPasswordPage.jsx
A  frontend/src/features/auth/VerifyEmailPage.jsx
A  frontend/src/features/auth/auth.test.jsx
A  frontend/src/features/auth/components/AuthHeader.jsx
A  frontend/src/features/auth/components/PasswordInput.jsx
A  frontend/src/features/auth/components/PasswordRequirements.jsx
A  frontend/src/features/auth/components/ResendVerification.jsx
A  frontend/src/features/auth/components/StatusPanel.jsx
A  frontend/src/features/auth/useAuthForm.js
A  frontend/src/features/auth/useTokenFromUrl.js
A  frontend/src/features/auth/validation.js
A  frontend/src/features/auth/validation.test.js
A  frontend/src/features/careerTracks/CareerTracksPage.jsx
A  frontend/src/features/careerTracks/careerTracks.test.jsx
A  frontend/src/features/dashboard/DashboardPage.jsx
A  frontend/src/features/dashboard/components/ApplicationsCard.jsx
A  frontend/src/features/dashboard/components/AssistantCard.jsx
A  frontend/src/features/dashboard/components/AtsCard.jsx
A  frontend/src/features/dashboard/components/DashboardCard.jsx
A  frontend/src/features/dashboard/components/HeroStats.jsx
A  frontend/src/features/dashboard/components/InterviewCard.jsx
A  frontend/src/features/dashboard/components/MatchCard.jsx
A  frontend/src/features/dashboard/components/ResumeCard.jsx
A  frontend/src/features/dashboard/components/ScoreRing.jsx
A  frontend/src/features/dashboard/components/SkillsCard.jsx
A  frontend/src/features/dashboard/dashboard.test.jsx
A  frontend/src/features/dashboard/format.js
A  frontend/src/features/documents/DocumentDetailPage.jsx
A  frontend/src/features/documents/DocumentsPage.jsx
A  frontend/src/features/documents/components/AiAssistChoice.jsx
A  frontend/src/features/documents/components/CreateDocumentForm.jsx
A  frontend/src/features/documents/components/DocumentEditor.jsx
A  frontend/src/features/documents/components/DocumentPreview.jsx
A  frontend/src/features/documents/components/FactCheckPanel.jsx
A  frontend/src/features/documents/components/InternshipPicker.jsx
A  frontend/src/features/documents/documentFormat.js
A  frontend/src/features/documents/documents.test.jsx
A  frontend/src/features/internships/BrowseInternships.jsx
A  frontend/src/features/internships/InternshipDetailPage.jsx
A  frontend/src/features/internships/InternshipsPage.jsx
A  frontend/src/features/internships/SemanticSearch.jsx
A  frontend/src/features/internships/components/InternshipCard.jsx
A  frontend/src/features/internships/internshipFormat.js
A  frontend/src/features/internships/internships.test.jsx
A  frontend/src/features/interviews/InterviewPrepPage.jsx
A  frontend/src/features/interviews/InterviewSessionPage.jsx
A  frontend/src/features/interviews/components/EvaluationView.jsx
A  frontend/src/features/interviews/components/QuestionCard.jsx
A  frontend/src/features/interviews/components/SessionSummary.jsx
A  frontend/src/features/interviews/components/StartSessionForm.jsx
A  frontend/src/features/interviews/components/SuggestedAnswer.jsx
A  frontend/src/features/interviews/interviewFormat.js
A  frontend/src/features/interviews/interviews.test.jsx
A  frontend/src/features/matches/ExploreJobs.jsx
A  frontend/src/features/matches/JobInsights.jsx
A  frontend/src/features/matches/MatchBreakdown.jsx
A  frontend/src/features/matches/MatchesPage.jsx
A  frontend/src/features/matches/matches.test.jsx
A  frontend/src/features/profile/ProfilePage.jsx
A  frontend/src/features/profile/components/BioEditor.jsx
A  frontend/src/features/profile/components/ProfilePhoto.jsx
A  frontend/src/features/profile/profile.test.jsx
A  frontend/src/features/profile/profileForm.js
A  frontend/src/features/resumes/ResumeComparePage.jsx
A  frontend/src/features/resumes/ResumesPage.jsx
A  frontend/src/features/resumes/components/ReadinessPanel.jsx
A  frontend/src/features/resumes/components/ResumeDetail.jsx
A  frontend/src/features/resumes/components/ResumeEditor.jsx
A  frontend/src/features/resumes/components/ResumeUploader.jsx
A  frontend/src/features/resumes/resumeData.js
A  frontend/src/features/resumes/resumeFile.js
A  frontend/src/features/resumes/resumes.test.jsx
A  frontend/src/features/resumes/versions.test.jsx
A  frontend/src/features/skillGaps/InternshipGapPage.jsx
A  frontend/src/features/skillGaps/SkillGapsPage.jsx
A  frontend/src/features/skillGaps/components/JobRoadmap.jsx
A  frontend/src/features/skillGaps/components/LearningPlan.jsx
A  frontend/src/features/skillGaps/components/ProgressSelect.jsx
A  frontend/src/features/skillGaps/components/RecommendationCard.jsx
A  frontend/src/features/skillGaps/gapFormat.js
A  frontend/src/features/skillGaps/skillGaps.test.jsx
M  frontend/src/features/system/ComingSoonPage.jsx
M  frontend/src/features/system/ForbiddenPage.jsx
M  frontend/src/features/system/NotFoundPage.jsx
A  frontend/src/hooks/useApiResource.js
M  frontend/src/index.css
M  frontend/src/layouts/AppLayout.jsx
M  frontend/src/layouts/AuthLayout.jsx
A  frontend/src/layouts/ProfileMenu.jsx
M  frontend/src/routes/AppRoutes.jsx
A  frontend/src/routes/GuestRoute.jsx
A  frontend/src/routes/PageBoundary.jsx
A  frontend/src/routes/PageBoundary.test.jsx
M  frontend/src/routes/navigation.js
M  frontend/src/test/handlers.js
M  frontend/src/test/setup.js
A  frontend/src/utils/saveBlob.js
M  frontend/tailwind.config.js
M  frontend/vite.config.js
A  migrations/versions/a7c9e1b3d5f6_profile_bio_avatar_and_resume_versions.py
A  migrations/versions/c6d2a8f4b1e3_account_security.py
A  migrations/versions/d8e4b2c6a9f1_invitations_and_email_log.py
A  migrations/versions/e1f3a5c7b9d2_skill_progress_and_job_sources.py
A  migrations/versions/f2b4d6a8c0e1_study_documents.py
M  requirements.txt
M  tests/conftest.py
A  tests/resume_factory.py
A  tests/test_admin_security.py
A  tests/test_assistant_product_rag.py
A  tests/test_assistant_product_rag_real_model.py
M  tests/test_document_generation.py
M  tests/test_documents_api.py
A  tests/test_e2e_workflow.py
A  tests/test_invitations.py
A  tests/test_job_matching_modes.py
A  tests/test_login_throttle.py
A  tests/test_mailer.py
M  tests/test_migrations.py
A  tests/test_model_unavailable.py
A  tests/test_ollama_provider.py
A  tests/test_p3_features.py
A  tests/test_prep_agent.py
A  tests/test_profile_and_versions.py
A  tests/test_resume_quality.py
M  tests/test_roles.py
A  tests/test_study_documents.py
A  tests/test_superadmin_cli.py
M  tests/test_vector_index.py
```

## 2. Modified after staging - must be re-staged (31 files)

```
.env.example
.gitignore
CAREERNOVA_DEMO_GUIDE.md
CAREERNOVA_HR_ASSIGNMENT_REPORT.md
CAREERNOVA_IMPLEMENTATION_REPORT.md
CAREERNOVA_TEST_REPORT.md
DEPLOYMENT_AND_HANDOVER_GUIDE.md
FINAL_DATABASE_MIGRATION_CHECKLIST.md
README.md
backend/data/product_docs/02_workflow.md
backend/data/product_docs/03_resume_upload.md
backend/database.py
backend/routes/internships.py
backend/routes/resumes.py
backend/services/assistant/service.py
backend/services/resume_parser.py
frontend/src/App.test.jsx
frontend/src/components/ui/EmptyState.jsx
frontend/src/features/assistant/assistant.test.jsx
frontend/src/features/assistant/assistantFormat.js
frontend/src/features/dashboard/components/HeroStats.jsx
frontend/src/features/dashboard/dashboard.test.jsx
frontend/src/features/resumes/ResumeComparePage.jsx
frontend/src/features/resumes/ResumesPage.jsx
frontend/src/features/resumes/components/ReadinessPanel.jsx
frontend/src/features/resumes/resumes.test.jsx
frontend/src/features/system/ForbiddenPage.jsx
frontend/src/features/system/NotFoundPage.jsx
frontend/src/test/handlers.js
tests/test_internships_api.py
tests/test_profile_and_versions.py
```

## 3. New, untracked - to add (7 files)

```
MANUAL_ACCEPTANCE_CHECKLIST.md
backend/services/assistant/app_guide.py
frontend/vercel.json
render.yaml
tests/test_app_guide.py
tests/test_project_extraction.py
tests/test_readiness_versions.py
```

## 4. Excluded by .gitignore (present on disk, never published)

```
.claude/
.env
.models/
.pytest_cache/
.pytest_tmp/
.venv/
Milestone_2_basics.zip
backend/__pycache__/
backend/data/faiss_index/
backend/data/faiss_index_test/
backend/routes/__pycache__/
backend/schemas/__pycache__/
backend/services/__pycache__/
backend/services/assistant/__pycache__/
backend/services/llm/__pycache__/
backend/services/prep/__pycache__/
backend/utils/__pycache__/
docs/assignment/evaluation/study_rag_eval_console.txt
frontend/.backups/
frontend/dist/
frontend/node_modules/
migrations/__pycache__/
migrations/versions/__pycache__/
uploads/
```

## 5. Scan results

- Release set: 310 paths (309 files + 1 deletion), 60,776 lines scanned: 0 secrets, 0 secret settings with values, 0 machine paths, 0 personal data (2 pattern hits were the CSS class `cn-card-interactive`; Gmail addresses are placeholders/test fixtures).
- Index: no tracked file matches an ignore rule. No binary files; largest file `frontend/package-lock.json` (161 kB).
- Git history of the branch (what a push publishes): 0 secrets, 0 personal data, 0 machine paths. The stash commits contain local paths but the stash is never pushed.
