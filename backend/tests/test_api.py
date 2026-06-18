import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_root(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "RecruitIQ" in response.json()["name"]


@pytest.mark.asyncio
async def test_upload_jd_text(client):
    response = await client.post(
        "/api/v1/upload-jd",
        data={"text": "Senior Python Developer needed. 5+ years experience. Must know FastAPI, PostgreSQL, AWS."},
    )
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert data["parsed_data"] is not None


@pytest.mark.asyncio
async def test_upload_jd_no_input(client):
    response = await client.post("/api/v1/upload-jd", data={})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_list_job_descriptions(client):
    response = await client.get("/api/v1/job-descriptions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_analytics(client):
    response = await client.get("/api/v1/analytics")
    assert response.status_code == 200
    data = response.json()
    assert "total_cvs" in data
    assert "score_distribution" in data


@pytest.mark.asyncio
async def test_list_candidates_filter_validation(client):
    response = await client.get("/api/v1/candidates?min_experience=2.5&max_experience=5.0&required_skills=Python,FastAPI")
    assert response.status_code != 422

