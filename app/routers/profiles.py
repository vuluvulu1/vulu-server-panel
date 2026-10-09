from fastapi import APIRouter, Request

from ..services.profiles import load_profiles
from ..templating import templates

router = APIRouter()


@router.get("/profiles")
async def profiles_page(request: Request):
    profiles, errors = load_profiles()
    return templates.TemplateResponse(request, "profiles.html", {"profiles": profiles, "errors": errors})
