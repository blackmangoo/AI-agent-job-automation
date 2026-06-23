"""
LLM Decision Brain
====================
Module 2: Uses Groq's LLaMA 3 70B model to analyze job listings,
determine eligibility, generate tailored responses, and answer
screening questions — all in strict JSON mode.

The brain constructs a detailed system prompt embedding the candidate's
full profile, then sends the scraped job data for analysis.
"""

import os
import json
from typing import Optional

from groq import Groq

from config.candidate_profile import CANDIDATE
from utils.logger import get_logger

logger = get_logger(__name__)

# Model configuration
MODEL = "llama3-70b-8192"
TEMPERATURE = 0.3
MAX_TOKENS = 2048

# JSON schema the LLM must produce
EXPECTED_SCHEMA = {
    "eligible": "boolean — true if candidate is a good match",
    "eligibility_reason": "string — one sentence explaining why or why not",
    "resume_objective": "string — exactly 2 sentences, tailored to this role, must echo JD keywords and reference a project",
    "confidence_score": "float 0.0–1.0 — how confident the match is",
    "screening_answers": [
        {
            "question": "exact question text",
            "answer": "precise answer based on candidate profile",
            "field_hint": "CSS selector or label text hint for form filling",
        }
    ],
    "cover_note": "string — optional 3-sentence personalized cover note",
}


def _build_system_prompt() -> str:
    """Build the system prompt with the full candidate profile.

    Returns:
        A detailed system prompt string instructing the LLM on its role,
        the candidate's background, and the exact JSON output format.
    """
    profile = CANDIDATE.to_prompt_string()

    return f"""You are an expert AI job application analyst. Your role is to analyze job listings
and determine if the candidate below is a good match, then generate tailored application content.

═══════════════════════════════════════
CANDIDATE PROFILE (YOUR KNOWLEDGE BASE)
═══════════════════════════════════════
{profile}

═══════════════════════════════════════
YOUR TASK
═══════════════════════════════════════
1. Analyze the job description provided by the user.
2. Determine if the candidate is eligible (consider both jobs AND internships as valid targets).
3. For fresh graduates, entry-level roles, and internships: be GENEROUS with eligibility.
   The candidate is a fresh graduate actively seeking both full-time roles and internships.
4. Generate a tailored resume objective that echoes keywords from the JD and references
   at least one of the candidate's projects by name.
5. Answer ALL screening questions accurately based on the candidate's profile.
   - For "years of experience" questions: count internship experience + project work.
   - For location/authorization questions: answer honestly based on Pakistan location.
   - For Yes/No questions about skills: check the candidate's skill list.
6. Write a brief, personalized cover note if applicable.

═══════════════════════════════════════
OUTPUT FORMAT (STRICT JSON — NO EXCEPTIONS)
═══════════════════════════════════════
You MUST respond with ONLY a valid JSON object matching this schema:
{{
    "eligible": true/false,
    "eligibility_reason": "One sentence explaining why or why not.",
    "resume_objective": "Exactly 2 sentences. Tailored to this specific role. Must echo keywords from the JD. Must reference at least one project from the candidate's profile.",
    "confidence_score": 0.85,
    "screening_answers": [
        {{
            "question": "Exact question text from the form",
            "answer": "Precise answer based on candidate profile",
            "field_hint": "CSS selector hint or label text for Playwright to locate this field"
        }}
    ],
    "cover_note": "Optional 3-sentence personalized cover note for this role."
}}

RULES:
- ONLY output valid JSON. No markdown, no explanations, no code fences.
- confidence_score must be a float between 0.0 and 1.0.
- screening_answers must include ALL questions provided, even if the answer is "N/A".
- Be honest — never fabricate skills or experience the candidate doesn't have.
- Consider internships, entry-level, and junior roles as eligible targets.
"""


def _build_user_prompt(scraped_data: dict, cv_text: str) -> str:
    """Build the user prompt with job data and CV text.

    Args:
        scraped_data: Dict from scraper module with job_title, company,
            description, and questions.
        cv_text: Plain text content of the candidate's CV.

    Returns:
        Formatted user prompt string.
    """
    questions_text = ""
    if scraped_data.get("questions"):
        questions_text = "\n\nSCREENING QUESTIONS FOUND ON THE FORM:\n"
        for i, q in enumerate(scraped_data["questions"], 1):
            questions_text += f"{i}. {q}\n"
    else:
        questions_text = "\n\nNo screening questions were found on this page."

    return f"""Analyze this job listing and generate your response:

JOB TITLE: {scraped_data.get('job_title', 'Unknown')}
COMPANY: {scraped_data.get('company', 'Unknown')}
URL: {scraped_data.get('url', 'N/A')}

JOB DESCRIPTION:
{scraped_data.get('description', 'No description available')}
{questions_text}

CANDIDATE'S CV TEXT:
{cv_text}

Now analyze and respond with the JSON object as specified."""


def analyze_job(scraped_data: dict, cv_text: str) -> dict:
    """Analyze a job listing and generate tailored application content.

    Calls the Groq LLM with the candidate's profile and job data to:
    - Determine eligibility
    - Generate a tailored resume objective
    - Answer screening questions
    - Create a personalized cover note

    Args:
        scraped_data: Dict from scraper module containing:
            - job_title (str)
            - company (str)
            - description (str)
            - questions (list[str])
        cv_text: Plain text of the candidate's CV.

    Returns:
        Parsed dict matching the expected JSON schema with keys:
        eligible, eligibility_reason, resume_objective, confidence_score,
        screening_answers, cover_note.

    Raises:
        RuntimeError: If the Groq API call fails or JSON parsing fails
            after retry.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY not found in environment. "
            "Please add it to your .env file."
        )

    client = Groq(api_key=api_key)

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(scraped_data, cv_text)

    logger.info(
        f"Analyzing job: '{scraped_data.get('job_title')}' at "
        f"'{scraped_data.get('company')}'"
    )

    # First attempt
    response = _call_groq(client, system_prompt, user_prompt)
    result = _parse_response(response)

    if result is not None:
        _log_analysis(result)
        return result

    # Retry with corrective prompt
    logger.warning("First LLM response failed JSON validation — retrying with correction")
    corrective_prompt = (
        "Your previous response was not valid JSON. Please respond with ONLY "
        "a valid JSON object matching the schema I specified. No markdown, no "
        "code fences, no explanations — just the raw JSON object."
    )

    response = _call_groq(
        client, system_prompt, user_prompt,
        retry_message=corrective_prompt,
        previous_response=response,
    )
    result = _parse_response(response)

    if result is not None:
        _log_analysis(result)
        return result

    raise RuntimeError(
        "Failed to get valid JSON from LLM after retry. "
        f"Last response: {response[:500]}"
    )


def _call_groq(
    client: Groq,
    system_prompt: str,
    user_prompt: str,
    retry_message: Optional[str] = None,
    previous_response: Optional[str] = None,
) -> str:
    """Make a call to the Groq API.

    Args:
        client: Initialized Groq client.
        system_prompt: The system prompt with candidate profile.
        user_prompt: The user prompt with job data.
        retry_message: Optional corrective message for retry attempts.
        previous_response: The LLM's previous (failed) response, if retrying.

    Returns:
        The raw text response from the LLM.

    Raises:
        RuntimeError: If the API call fails.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    if retry_message and previous_response:
        messages.append({"role": "assistant", "content": previous_response})
        messages.append({"role": "user", "content": retry_message})

    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            response_format={"type": "json_object"},
        )

        response_text = completion.choices[0].message.content
        logger.debug(f"Groq response ({len(response_text)} chars): {response_text[:200]}...")

        return response_text

    except Exception as e:
        logger.error(f"Groq API call failed: {e}")
        raise RuntimeError(f"Groq API call failed: {e}")


def _parse_response(response_text: str) -> Optional[dict]:
    """Parse and validate the LLM's JSON response.

    Args:
        response_text: Raw text response from the LLM.

    Returns:
        Parsed dict if valid, None if parsing fails.
    """
    try:
        # Clean potential markdown code fences
        text = response_text.strip()
        if text.startswith("```"):
            # Remove code fence markers
            lines = text.split("\n")
            text = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            )

        data = json.loads(text)

        # Validate required keys
        required_keys = ["eligible", "eligibility_reason", "resume_objective",
                         "confidence_score", "screening_answers"]
        missing = [k for k in required_keys if k not in data]

        if missing:
            logger.warning(f"Response missing keys: {missing}")
            # Set defaults for missing optional fields
            data.setdefault("cover_note", "")
            data.setdefault("screening_answers", [])
            data.setdefault("confidence_score", 0.5)

            if "eligible" not in data or "eligibility_reason" not in data:
                return None

        # Ensure confidence_score is a float
        data["confidence_score"] = float(data.get("confidence_score", 0.5))

        # Ensure screening_answers is a list
        if not isinstance(data.get("screening_answers"), list):
            data["screening_answers"] = []

        return data

    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse error: {e}")
        return None
    except Exception as e:
        logger.warning(f"Response validation error: {e}")
        return None


def _log_analysis(result: dict) -> None:
    """Log the analysis results at INFO level.

    Args:
        result: The parsed analysis dict.
    """
    eligible_emoji = "✅" if result["eligible"] else "❌"
    logger.info(
        f"{eligible_emoji} Eligibility: {result['eligible']} "
        f"(confidence: {result['confidence_score']:.0%})"
    )
    logger.info(f"Reason: {result['eligibility_reason']}")
    logger.info(f"Resume objective: {result['resume_objective']}")

    if result.get("screening_answers"):
        logger.info(f"Screening answers prepared: {len(result['screening_answers'])}")
        for ans in result["screening_answers"]:
            logger.debug(f"  Q: {ans.get('question', 'N/A')}")
            logger.debug(f"  A: {ans.get('answer', 'N/A')}")

    if result.get("cover_note"):
        logger.info(f"Cover note: {result['cover_note'][:100]}...")
