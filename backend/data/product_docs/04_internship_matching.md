# Internship discovery and matching

## Finding internships
On the Internships page you can browse active internships and filter them by keyword, domain, work mode, location and skill. AI search lets you describe the internship you want in your own words; it finds postings with a similar meaning using semantic search over a FAISS vector index. You can save internships for later.

## How matching works
Matching ranks internships against your latest parsed resume. It retrieves candidate internships from the vector index (combined with every internship that shares a skill with you), reads each one from the database, and then calculates a transparent compatibility score.

## The compatibility score
The score is out of 100 and combines four components: skills (50%), semantic similarity between your profile and the posting (20%), education (15%) and location or work mode (15%). Labels are Excellent (80 and above), Strong (65 and above), Fair (45 and above) and Weak (below 45). Missing information lowers the score rather than inflating it, and a match with no required skill is capped at 50.

## Reading a match explanation
Each match shows the matched and missing required and preferred skills, one sentence for each score component, any score caps that were applied and any information that was missing. From a match you can open its skill gaps and learning plan, or tailor your resume for it.

## Skill gaps and learning plans
Skill-gap analysis compares your skills with an internship's requirements. Missing skills are prioritised (required skills before preferred ones), and each comes with a learning plan of topics, prerequisites and an estimated time. You can mark a skill as in progress, completed or dismissed.
