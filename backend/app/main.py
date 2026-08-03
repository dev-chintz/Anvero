from fastapi import FastAPI

app = FastAPI(
    title="Anvero API",
    version="0.1.0",
)


@app.get("/")
def root():
    return {
        "message": "Welcome to Anvero API",
        "status": "running",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
    }