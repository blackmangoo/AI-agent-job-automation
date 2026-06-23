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
    """Complete candidate profile for Ammar Akbar."""
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
        """Serialize the full profile into a formatted string for LLM prompts."""
        sections = []
        sections.append(f"CANDIDATE: {self.full_name}")
        sections.append(f"STATUS: {self.status}")
        sections.append(f"DEGREE: {self.degree} \u2014 {self.university} ({self.graduation})")
        sections.append(f"LOCATION: {self.location}")
        sections.append(f"EMAIL: {self.email}")
        sections.append(f"PHONE: {self.phone}")
        sections.append(f"PORTFOLIO: {self.portfolio}")
        sections.append(f"GITHUB: {self.github}")
        sections.append(f"LINKEDIN: {self.linkedin}")
        sections.append("")
        sections.append(f"PROFESSIONAL SUMMARY:\n{self.summary}")
        sections.append("")
        sections.append("TARGET ROLES:")
        for role in self.target_roles:
            sections.append(f"  - {role}")
        sections.append("")
        sections.append("TECHNICAL SKILLS:")
        sections.append(f"  Languages: {', '.join(self.languages)}")
        sections.append(f"  AI/ML: {', '.join(self.ai_ml_skills)}")
        sections.append(f"  Models & Libraries: {', '.join(self.models_libraries)}")
        sections.append(f"  Backend & APIs: {', '.join(self.backend_apis)}")
        sections.append(f"  Frontend/Mobile: {', '.join(self.frontend_mobile)}")
        sections.append(f"  Databases & Cloud: {', '.join(self.databases_cloud)}")
        sections.append(f"  Tools: {', '.join(self.tools)}")
        sections.append("")
        sections.append("WORK EXPERIENCE:")
        for exp in self.experiences:
            sections.append(f"\n  {exp.title} @ {exp.company} ({exp.duration})")
            for h in exp.highlights:
                sections.append(f"    \u2022 {h}")
        sections.append("")
        sections.append("PROJECTS:")
        for proj in self.projects:
            sections.append(f"\n  {proj.name} \u2014 {proj.description}")
            sections.append(f"  Tech Stack: {proj.tech_stack}")
            for h in proj.highlights:
                sections.append(f"    \u2022 {h}")
        return "\n".join(sections)


# Singleton instance
CANDIDATE = CandidateProfile(
    full_name="Ammar Akbar",
    email="ammar.akbar2002@gmail.com",
    phone="+92 321 4797778",
    location="Islamabad / Lahore, Pakistan",
    linkedin="https://linkedin.com/in/ammar-akbar2002",
    github="https://github.com/blackmangoo",
    portfolio="https://ammar.works",
    degree="Bachelor of Science in Artificial Intelligence",
    university="FAST \u2014 National University of Computer and Emerging Sciences",
    graduation="Expected June 2026",
    status="Fresh Graduate",
    summary=("AI/ML engineer and BS Artificial Intelligence graduate (FAST-NUCES, 2026) "
             "specializing in computer vision, RAG pipelines, and LLM fine-tuning. "
             "Builds deployable AI systems end-to-end. Open to full-time AI/ML engineering roles and internships."),
    target_roles=["AI/ML Engineer / Research Intern", "Computer Vision Engineer",
                  "LLM / Generative AI Developer", "Backend Developer (Python / FastAPI)",
                  "AI Intern / ML Intern"],
    languages=["Python", "Dart", "JavaScript", "C++", "SQL"],
    ai_ml_skills=["Machine Learning", "Deep Learning", "NLP", "Computer Vision",
                  "LLMs", "RAG", "LoRA Fine-Tuning", "Prompt Engineering",
                  "Model Evaluation", "Feature Engineering"],
    models_libraries=["YOLOv11", "BERT", "GPT-Neo", "DistilRoBERTa", "BART-large-MNLI",
                      "XGBoost", "Scikit-learn", "PyTorch", "Hugging Face",
                      "SentenceTransformers", "FAISS", "LangChain"],
    backend_apis=["FastAPI", "Node.js", "Express.js", "Streamlit", "REST APIs"],
    frontend_mobile=["Flutter (Dart)", "React", "Next.js", "Tailwind CSS"],
    databases_cloud=["Supabase", "PostgreSQL", "Firebase", "Vercel", "Docker"],
    tools=["Git", "GitHub", "Postman", "n8n", "GitHub Actions"],
    experiences=[
        WorkExperience(title="AI/ML Engineering Intern", company="DevelopersHub Corporation",
                       duration="Apr 2026 \u2013 Jun 2026",
                       highlights=["Delivered 5 AI systems in 6 weeks: LLMs, RAG, NLP classification, regression, and Streamlit deployments.",
                                   "Built Serene \u2014 mental health chatbot with GPT-Neo-125M LoRA fine-tuning, DistilRoBERTa emotion detection, FAISS retrieval, Supabase memory.",
                                   "Developed DocuMind, NewsLens (94% accuracy), and TicketIQ.",
                                   "Built Luxe Estate \u2014 XGBoost regression on 1M+ row housing dataset with Dockerized Streamlit UI."]),
        WorkExperience(title="AI Developer Intern", company="Nexium",
                       duration="Jun 2025 \u2013 Aug 2025",
                       highlights=["Shipped full-stack AI apps using React, Next.js, Supabase, n8n, and Gemini API.",
                                   "Built AI Recipe Generator and Blog Summariser & Translator."]),
        WorkExperience(title="Teaching Assistant", company="FAST-NUCES",
                       duration="Sep 2024 \u2013 Jun 2025",
                       highlights=["Mentored 60+ students in C++ programming, debugging, and project development."]),
    ],
    projects=[
        Project(name="OmniDrive AI", description="Automotive Diagnostic Platform (FYP)",
                tech_stack="Flutter, FastAPI, YOLOv11-Large, Supabase, Firebase FCM, Kalman Filter, OBD-II",
                highlights=["99.1% top-1 accuracy on 50 car-part classes.",
                            "GPS/IMU Kalman-filter sensor fusion for performance testing.",
                            "4-role marketplace with atomic stock RPCs and Admin TOTP MFA."]),
        Project(name="Serene", description="AI Wellness Companion",
                tech_stack="LoRA, GPT-Neo-125M, DistilRoBERTa, FAISS, Supabase, Streamlit",
                highlights=["LoRA fine-tuned LLM with emotion detection and crisis-safety handling."]),
        Project(name="NewsLens & TicketIQ", description="Applied NLP Systems",
                tech_stack="BERT, BART-large-MNLI, Hugging Face, Streamlit",
                highlights=["BERT fine-tuned for 4-class news classification (94% accuracy)."]),
    ],
)
