"""
Candidate Profile Configuration
================================
Stores Ammar Akbar's professional profile as a structured dataclass.
This is the single source of truth used by the LLM Brain for system prompts
and by the Form Filler for auto-populating application fields.
"""

from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class WorkExperience:
    """Represents a single work experience entry."""
    title: str
    company: str
    duration: str
    highlights: List[str]


@dataclass
class Project:
    """Represents a portfolio project."""
    name: str
    description: str
    tech_stack: str
    highlights: List[str]


@dataclass
class CandidateProfile:
    """Complete candidate profile for Ammar Akbar.

    This dataclass is the agent's core identity. All LLM prompts and
    form-filling logic reference this single source of truth.
    """
    full_name: str
    email: str
    phone: str
    location: str
    linkedin: str
    github: str
    portfolio: str
    degree: str
    university: str
    graduation: str
    status: str
    summary: str
    target_roles: List[str]
    languages: List[str]
    ai_ml_skills: List[str]
    models_libraries: List[str]
    backend_apis: List[str]
    frontend_mobile: List[str]
    databases_cloud: List[str]
    tools: List[str]
    experiences: List[WorkExperience]
    projects: List[Project]

    def to_prompt_string(self) -> str:
        """Serialize the full profile into a formatted string for LLM prompts.

        Returns:
            A multi-line string containing all candidate information,
            formatted for embedding in an LLM system prompt.
        """
        sections = []

        # Header
        sections.append(f"CANDIDATE: {self.full_name}")
        sections.append(f"STATUS: {self.status}")
        sections.append(f"DEGREE: {self.degree} — {self.university} ({self.graduation})")
        sections.append(f"LOCATION: {self.location}")
        sections.append(f"EMAIL: {self.email}")
        sections.append(f"PHONE: {self.phone}")
        sections.append(f"PORTFOLIO: {self.portfolio}")
        sections.append(f"GITHUB: {self.github}")
        sections.append(f"LINKEDIN: {self.linkedin}")
        sections.append("")

        # Summary
        sections.append(f"PROFESSIONAL SUMMARY:\n{self.summary}")
        sections.append("")

        # Target roles
        sections.append("TARGET ROLES:")
        for role in self.target_roles:
            sections.append(f"  - {role}")
        sections.append("")

        # Technical skills
        sections.append("TECHNICAL SKILLS:")
        sections.append(f"  Languages: {', '.join(self.languages)}")
        sections.append(f"  AI/ML: {', '.join(self.ai_ml_skills)}")
        sections.append(f"  Models & Libraries: {', '.join(self.models_libraries)}")
        sections.append(f"  Backend & APIs: {', '.join(self.backend_apis)}")
        sections.append(f"  Frontend/Mobile: {', '.join(self.frontend_mobile)}")
        sections.append(f"  Databases & Cloud: {', '.join(self.databases_cloud)}")
        sections.append(f"  Tools: {', '.join(self.tools)}")
        sections.append("")

        # Work experience
        sections.append("WORK EXPERIENCE:")
        for exp in self.experiences:
            sections.append(f"\n  {exp.title} @ {exp.company} ({exp.duration})")
            for h in exp.highlights:
                sections.append(f"    • {h}")
        sections.append("")

        # Projects
        sections.append("PROJECTS:")
        for proj in self.projects:
            sections.append(f"\n  {proj.name} — {proj.description}")
            sections.append(f"  Tech Stack: {proj.tech_stack}")
            for h in proj.highlights:
                sections.append(f"    • {h}")

        return "\n".join(sections)


# ============================================================
# Singleton instance — import this wherever the profile is needed
# ============================================================
CANDIDATE = CandidateProfile(
    full_name="Ammar Akbar",
    email="ammar.akbar2002@gmail.com",
    phone="+92 321 4797778",
    location="Islamabad / Lahore, Pakistan",
    linkedin="https://linkedin.com/in/ammar-akbar2002",
    github="https://github.com/blackmangoo",
    portfolio="https://ammar.works",
    degree="Bachelor of Science in Artificial Intelligence",
    university="FAST — National University of Computer and Emerging Sciences",
    graduation="Expected June 2026",
    status="Fresh Graduate",
    summary=(
        "AI/ML engineer and BS Artificial Intelligence graduate (FAST-NUCES, 2026) "
        "specializing in computer vision, RAG pipelines, and LLM fine-tuning. "
        "Builds deployable AI systems end-to-end — from model training to production "
        "APIs and mobile interfaces. Open to full-time AI/ML engineering roles and internships."
    ),
    target_roles=[
        "AI/ML Engineer / Research Intern",
        "Computer Vision Engineer",
        "LLM / Generative AI Developer",
        "Backend Developer (Python / FastAPI)",
        "AI Intern / ML Intern",
    ],
    languages=["Python", "Dart", "JavaScript", "C++", "SQL"],
    ai_ml_skills=[
        "Machine Learning", "Deep Learning", "NLP", "Computer Vision",
        "LLMs", "RAG", "LoRA Fine-Tuning", "Prompt Engineering",
        "Model Evaluation", "Feature Engineering",
    ],
    models_libraries=[
        "YOLOv11", "BERT", "GPT-Neo", "DistilRoBERTa", "BART-large-MNLI",
        "XGBoost", "Scikit-learn", "PyTorch", "Hugging Face",
        "SentenceTransformers", "FAISS", "LangChain",
    ],
    backend_apis=["FastAPI", "Node.js", "Express.js", "Streamlit", "REST APIs"],
    frontend_mobile=["Flutter (Dart)", "React", "Next.js", "Tailwind CSS"],
    databases_cloud=["Supabase", "PostgreSQL", "Firebase", "Vercel", "Docker"],
    tools=["Git", "GitHub", "Postman", "n8n", "GitHub Actions"],
    experiences=[
        WorkExperience(
            title="AI/ML Engineering Intern",
            company="DevelopersHub Corporation",
            duration="Apr 2026 – Jun 2026",
            highlights=[
                "Delivered 5 AI systems in 6 weeks: LLMs, RAG, NLP classification, regression, and Streamlit deployments.",
                "Built Serene — mental health chatbot with GPT-Neo-125M LoRA fine-tuning, "
                "DistilRoBERTa emotion detection (7 states), FAISS wellness retrieval, "
                "Supabase memory, and crisis-safety overrides.",
                "Developed DocuMind (RAG chatbot: MiniLM embeddings + FAISS + LangChain memory), "
                "NewsLens (BERT fine-tuned on AG News, 94% test accuracy), and "
                "TicketIQ (BART-large-MNLI zero-shot tagging).",
                "Built Luxe Estate — XGBoost regression on 1M+ row housing dataset with "
                "feature engineering and Dockerized Streamlit UI.",
            ],
        ),
        WorkExperience(
            title="AI Developer Intern",
            company="Nexium",
            duration="Jun 2025 – Aug 2025",
            highlights=[
                "Shipped full-stack AI apps using React, Next.js, Supabase, n8n, and Gemini API, deployed to production on Vercel.",
                "Sole developer of an AI Recipe Generator (n8n + Gemini API + Supabase magic-link auth + "
                "real-time dashboard) and a Blog Summariser & Translator (React, Node.js, jsdom scraping, "
                "Supabase — live at Vercel).",
            ],
        ),
        WorkExperience(
            title="Teaching Assistant — Programming Fundamentals",
            company="FAST-NUCES",
            duration="Sep 2024 – Jun 2025",
            highlights=[
                "Mentored 60+ students across two semesters in C++ programming, debugging, and project development.",
            ],
        ),
    ],
    projects=[
        Project(
            name="OmniDrive AI",
            description="Automotive Diagnostic Platform (Final Year Project)",
            tech_stack="Flutter, FastAPI, YOLOv11-Large, Supabase, Firebase FCM, Kalman Filter, OBD-II",
            highlights=[
                "Trained YOLO11-Large on 26,820 images across 50 car-part classes (100 epochs, Kaggle GPU) "
                "— 99.1% top-1 accuracy, ~110ms CPU inference served via FastAPI /predict.",
                "Built GPS/IMU Kalman-filter sensor fusion for real-time 0-60, 0-100 km/h, "
                "quarter-mile, and braking tests; OBD-II ELM327 WiFi for ground-truth speed.",
                "Architected a 4-role marketplace (customer, vendor, rider, admin) with atomic stock RPCs, "
                "Firebase FCM push notifications, and Admin TOTP MFA — 49 Dart files, 13 PostgreSQL tables.",
            ],
        ),
        Project(
            name="Serene",
            description="AI Wellness Companion",
            tech_stack="LoRA, GPT-Neo-125M, DistilRoBERTa, FAISS, Supabase, Streamlit",
            highlights=[
                "Fine-tuned GPT-Neo-125M with LoRA; combined local emotion detection, "
                "FAISS retrieval, and Supabase memory for context-aware multi-turn support "
                "with crisis-safety handling.",
            ],
        ),
        Project(
            name="NewsLens & TicketIQ",
            description="Applied NLP Systems",
            tech_stack="BERT, BART-large-MNLI, Hugging Face, Streamlit",
            highlights=[
                "Fine-tuned BERT for 4-class news classification (94% test accuracy); "
                "TicketIQ uses BART-large-MNLI for zero-shot and few-shot ticket tagging.",
            ],
        ),
    ],
)
