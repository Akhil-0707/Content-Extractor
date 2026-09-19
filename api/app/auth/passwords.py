from fastapi import HTTPException, status

from app.config import settings


def validate_new_password(password: str, username: str) -> None:
    problems = []
    if len(password) < settings.min_password_length:
        problems.append(f"at least {settings.min_password_length} characters")
    if password.lower() == password or password.upper() == password:
        problems.append("both upper- and lower-case letters")
    if not any(c.isdigit() for c in password):
        problems.append("at least one digit")
    if username.lower() in password.lower():
        problems.append("must not contain the username")
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Password needs: " + ", ".join(problems))
