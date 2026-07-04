from fastapi import FastAPI

app = FastAPI(title="Distributed Job Scheduler")

# Routers are added here as they are implemented (Phase 2+):
# from app.routers import auth, orgs, projects, queues, jobs, workers
# app.include_router(auth.router)
# app.include_router(orgs.router)
# app.include_router(projects.router)
# app.include_router(queues.router)
# app.include_router(jobs.router)
# app.include_router(workers.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
