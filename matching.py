import re

SKILLS = {
    # Languages
    "Python": ["python"],
    "Java": ["java"],
    "JavaScript": ["javascript", "js", "es6"],
    "TypeScript": ["typescript", "ts"],
    "C++": ["c\\+\\+", "cpp"],
    "C#": ["c#", "c sharp"],
    "Go": ["golang"],
    "Rust": ["rust"],
    "Kotlin": ["kotlin"],
    "Swift": ["swift"],
    "PHP": ["php"],
    "Ruby": ["ruby"],
    "Scala": ["scala"],
    "Dart": ["dart"],
    "SQL": ["sql"],
    "Bash": ["bash", "shell scripting"],
    # Frontend
    "HTML": ["html", "html5"],
    "CSS": ["css", "css3"],
    "React": ["react", "reactjs", "react\\.js"],
    "Next.js": ["next\\.js", "nextjs"],
    "Angular": ["angular", "angularjs"],
    "Vue": ["vue", "vuejs", "vue\\.js"],
    "Redux": ["redux"],
    "Tailwind CSS": ["tailwind", "tailwindcss"],
    "Bootstrap": ["bootstrap"],
    "React Native": ["react native"],
    "Flutter": ["flutter"],
    # Backend
    "Node.js": ["node", "nodejs", "node\\.js"],
    "Express.js": ["express", "expressjs", "express\\.js"],
    "Django": ["django"],
    "Flask": ["flask"],
    "FastAPI": ["fastapi"],
    "Spring Boot": ["spring boot", "springboot", "spring"],
    "Hibernate": ["hibernate"],
    ".NET": ["\\.net", "dotnet", "asp\\.net"],
    "Laravel": ["laravel"],
    "REST APIs": ["restful", "rest api", "rest apis"],
    "GraphQL": ["graphql"],
    "Microservices": ["microservices", "microservice"],
    "WebSockets": ["websocket", "websockets", "socket\\.io"],
    # Databases
    "MongoDB": ["mongodb", "mongo", "mongoose"],
    "MySQL": ["mysql"],
    "PostgreSQL": ["postgresql", "postgres"],
    "Redis": ["redis"],
    "Firebase": ["firebase"],
    "Oracle": ["oracle"],
    "DynamoDB": ["dynamodb"],
    "Elasticsearch": ["elasticsearch"],
    # Cloud & DevOps
    "AWS": ["aws", "amazon web services"],
    "Azure": ["azure"],
    "GCP": ["gcp", "google cloud"],
    "Docker": ["docker"],
    "Kubernetes": ["kubernetes", "k8s"],
    "CI/CD": ["ci/cd", "ci cd", "continuous integration"],
    "Jenkins": ["jenkins"],
    "GitHub Actions": ["github actions"],
    "Terraform": ["terraform"],
    "Linux": ["linux", "unix"],
    "Git": ["git", "github", "gitlab"],
    "Nginx": ["nginx"],
    # Data & AI
    "Machine Learning": ["machine learning", "ml"],
    "Deep Learning": ["deep learning"],
    "NLP": ["nlp", "natural language processing"],
    "Computer Vision": ["computer vision", "opencv"],
    "Generative AI": ["generative ai", "genai", "llm", "llms"],
    "TensorFlow": ["tensorflow"],
    "PyTorch": ["pytorch"],
    "Scikit-learn": ["scikit-learn", "sklearn"],
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "Data Analysis": ["data analysis", "data analytics"],
    "Power BI": ["power bi", "powerbi"],
    "Tableau": ["tableau"],
    "Excel": ["excel"],
    "Spark": ["spark", "pyspark"],
    "Hadoop": ["hadoop"],
    "LangChain": ["langchain"],
    # Testing
    "Jest": ["jest"],
    "Selenium": ["selenium"],
    "Cypress": ["cypress"],
    "PyTest": ["pytest"],
    "JUnit": ["junit"],
    "Unit Testing": ["unit testing", "unit tests"],
    # Fundamentals & practices
    "Data Structures": ["data structures", "dsa"],
    "Algorithms": ["algorithms"],
    "OOP": ["oop", "oops", "object oriented", "object-oriented"],
    "System Design": ["system design"],
    "DBMS": ["dbms"],
    "Operating Systems": ["operating systems"],
    "Computer Networks": ["computer networks", "networking"],
    "Agile": ["agile", "scrum"],
    "Jira": ["jira"],
    "Figma": ["figma"],
    "Postman": ["postman"],
    "Communication": ["communication skills", "communication"],
}

_STACKS = {
    "mern": ["MongoDB", "Express.js", "React", "Node.js"],
    "mean": ["MongoDB", "Express.js", "Angular", "Node.js"],
}

_PATTERNS = {
    name: re.compile(r"(?<![\w+#.])(?:" + "|".join(aliases) + r")(?![\w+#])", re.I)
    for name, aliases in SKILLS.items()
}


def extract_skills(text: str) -> set[str]:
    if not text:
        return set()

    found = {name for name, pattern in _PATTERNS.items() if pattern.search(text)}
    lowered = text.lower()
    for stack, skills in _STACKS.items():
        if re.search(rf"\b{stack}\b", lowered):
            found.update(skills)
    return found


def match_score(resume_skills: set[str], job_text: str) -> dict | None:
    job_skills = extract_skills(job_text)
    if not job_skills:
        return None

    matched = sorted(job_skills & resume_skills)
    missing = sorted(job_skills - resume_skills)
    return {
        "score": round(100 * len(matched) / len(job_skills)),
        "matched": matched,
        "missing": missing,
    }
